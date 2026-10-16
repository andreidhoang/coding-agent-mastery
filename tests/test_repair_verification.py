"""Controller mocks never execute/import candidate code in the host interpreter."""

import copy
import json
import os

import pytest

from service.artifacts import canonical_bytes
from service.execution import tree_digest
from service.repair_verification import (
    BRIDGE_PATH,
    DEFAULT_LIMITS,
    PythonFunctionRecipe,
    PythonFunctionVerifier,
)


def config():
    return {
        "schema": "python-function-recipe-v1",
        "recipe_id": "arithmetic-v1",
        "source_paths": ["calc.py"],
        "module_path": "calc.py",
        "functions": ["add"],
        "worker_cases": [
            {"id": "public-one", "function": "add", "args": [0, 1], "kwargs": {}, "expect": {"value": 1}}
        ],
        "final_cases": [
            {
                "id": "secret-case-name",
                "function": "add",
                "args": [11, 31],
                "kwargs": {},
                "expect": {"value": 42},
            }
        ],
    }


class SandboxFactory:
    __module__ = __name__
    __qualname__ = "SandboxFactory"

    def __init__(self, replies=None, close=None, on_start=None, start_error=None, run_error=None):
        self.replies = list(replies or [])
        self.close_result = close or {"retired": True}
        self.on_start = on_start
        self.start_error = start_error
        self.run_error = run_error
        self.instances = []
        self.live = 0
        self.max_live = 0

    def __call__(self, image, **limits):
        owner = self

        class Sandbox:
            def __init__(self):
                self.limits = limits
                self.image = image
                self.files = None
                self.request = None
                self.closed = False

            def start(self, files):
                self.files = dict(files)
                owner.live += 1
                owner.max_live = max(owner.live, owner.max_live)
                if owner.on_start:
                    owner.on_start(self)
                if owner.start_error:
                    raise owner.start_error

            def run(self, argv, max_output):
                assert argv[:3] == ["python", "-I", "/workspace/" + BRIDGE_PATH]
                self.request = json.loads(argv[3])
                self.max_output = max_output
                assert "expect" not in self.request
                if owner.run_error:
                    raise owner.run_error
                reply = owner.replies.pop(0) if owner.replies else {"value": 1}
                response = {
                    "schema": 1,
                    "request_id": self.request["request_id"],
                    "ok": True,
                    "value": reply.get("value"),
                }
                if "error_type" in reply:
                    response = {
                        "schema": 1,
                        "request_id": self.request["request_id"],
                        "ok": False,
                        "error_type": reply["error_type"],
                        "message": reply.get("message", ""),
                    }
                if "envelope" in reply:
                    response = reply["envelope"](response)
                return {
                    "output": reply.get("output", canonical_bytes(response).decode()),
                    "exit_code": reply.get("exit_code", 0),
                    "reason": reply.get("reason", "exited"),
                    "duration_seconds": 0.01,
                    "truncated": reply.get("truncated", False),
                    "process_group_retired": reply.get("process_group_retired", True),
                }

            def close(self):
                if isinstance(owner.close_result, Exception):
                    raise owner.close_result
                if not self.closed:
                    owner.live -= 1
                    self.closed = True
                return copy.deepcopy(owner.close_result)

        sandbox = Sandbox()
        self.instances.append(sandbox)
        return sandbox


def verifier(factory, recipe=None):
    return PythonFunctionVerifier("mock-image", sandbox_factory=factory, recipe=recipe)


def test_correct_public_and_private_checks_are_host_owned_and_sanitized():
    recipe = PythonFunctionRecipe.from_dict(config())
    factory = SandboxFactory([{"value": 1}, {"value": 42}])
    checker = verifier(factory, recipe)
    public = checker.verify({"calc.py": "unexecuted host text"}, recipe)
    final = checker.verify({"calc.py": "unexecuted host text"}, recipe, purpose="final")
    assert public["passed"] and final["passed"]
    assert final["environment_digest"] == checker.environment_digest
    assert final["phase"] == "final"
    assert final["retirement"]["retired"] is True
    assert final["cases"] == [{"id": "private-1", "passed": True, "category": "pass"}]
    assert "secret-case-name" not in json.dumps(final)
    assert factory.max_live == 1
    assert all(set(instance.files) == {"calc.py", BRIDGE_PATH} for instance in factory.instances)
    assert all("expect" not in json.dumps(instance.request) for instance in factory.instances)
    assert "final_cases" not in recipe.public_description()
    assert "secret-case-name" not in json.dumps(recipe.public_description())


def test_case_isolation_and_source_recipe_immutability():
    trusted = config()
    trusted["worker_cases"].append({**trusted["worker_cases"][0], "id": "public-two"})
    recipe = PythonFunctionRecipe.from_dict(trusted)
    expected_grader = recipe.grader_digest
    expected_files = {"calc.py": "original"}
    source = dict(expected_files)

    def mutate(instance):
        source["calc.py"] = "changed"
        trusted["worker_cases"][0]["expect"]["value"] = 99
        recipe.as_dict()["worker_cases"][0]["expect"]["value"] = 100
        instance.files["calc.py"] = "sandbox-self-modified"

    factory = SandboxFactory(on_start=mutate)
    result = verifier(factory).verify(source, recipe)
    assert result["passed"]
    assert result["tree_digest"] == tree_digest(expected_files)
    assert result["grader_digest"] == expected_grader
    assert factory.max_live == 1
    assert len(factory.instances) == 2
    assert factory.instances[0].limits["identity"] != factory.instances[1].limits["identity"]


@pytest.mark.parametrize(
    "reply",
    [
        {"value": True},
        {"value": "1"},
        {"error_type": "ValueError"},
        {"value": 2},
    ],
)
def test_complete_wrong_or_wrong_type_response_fails_assertion(reply):
    recipe = PythonFunctionRecipe.from_dict(config())
    result = verifier(SandboxFactory([reply])).verify({"calc.py": "candidate"}, recipe)
    assert result["outcome"] == "fail"
    assert not result["passed"]
    assert result["cases"][0]["category"] == "assertion_mismatch"
    assert not result["boundary_failures"]


@pytest.mark.parametrize(
    "reply",
    [
        {"output": "PASS"},
        {"output": '{"passed":true}'},
        {"output": '{"ok":true,"ok":false}'},
        {"output": "{} {}"},
        {"exit_code": 1},
        {"reason": "timeout"},
        {"reason": "output_limit"},
        {"reason": "untrusted hidden diagnostic"},
        {"truncated": True},
        {"process_group_retired": False},
        {"envelope": lambda r: {**r, "extra": True}},
        {"envelope": lambda r: {**r, "schema": True}},
        {"envelope": lambda r: {**r, "request_id": "wrong"}},
        {"envelope": lambda r: {**r, "ok": 1}},
        {"value": 1.0},
    ],
)
def test_protocol_process_faults_latch_error(reply):
    trusted = config()
    trusted["worker_cases"].append({**trusted["worker_cases"][0], "id": "public-two"})
    recipe = PythonFunctionRecipe.from_dict(trusted)
    factory = SandboxFactory([reply, {"value": 1}])
    result = verifier(factory).verify({"calc.py": "candidate"}, recipe)
    assert result["outcome"] == "error"
    assert result["retirement"]["retired"]
    assert not result["passed"]
    assert len(factory.instances) == 1
    assert result["boundary_failures"]
    assert "untrusted hidden diagnostic" not in json.dumps(result)


def test_expected_error_requires_complete_valid_transport_and_redacts_message():
    trusted = config()
    trusted["final_cases"][0]["expect"] = {"error_type": "ValueError"}
    recipe = PythonFunctionRecipe.from_dict(trusted)
    reply = {"error_type": "ValueError", "message": "private input echoed 11 31"}
    good = verifier(SandboxFactory([reply])).verify({"calc.py": "candidate"}, recipe, purpose="final")
    bad = verifier(SandboxFactory([{**reply, "reason": "timeout"}])).verify(
        {"calc.py": "candidate"}, recipe, purpose="final"
    )
    assert good["passed"]
    assert bad["outcome"] == "error"
    assert "private input echoed" not in json.dumps(good)
    assert "private input echoed" not in json.dumps(bad)


@pytest.mark.parametrize("cleanup", [{"retired": False}, {"retired": 1}, {}, RuntimeError("secret cleanup")])
def test_cleanup_uncertainty_retains_slot_stops_next_case(cleanup):
    trusted = config()
    trusted["worker_cases"].append({**trusted["worker_cases"][0], "id": "public-two"})
    recipe = PythonFunctionRecipe.from_dict(trusted)
    factory = SandboxFactory(close=cleanup)
    # Empty dict must be tested as actual absent confirmation.
    factory.close_result = cleanup
    result = verifier(factory).verify({"calc.py": "candidate"}, recipe)
    assert not result["retirement"]["retired"]
    assert result["outcome"] == "error"
    assert len(factory.instances) == 1
    assert "secret cleanup" not in json.dumps(result)


@pytest.mark.parametrize("stage", ["start", "run"])
def test_original_fault_and_cleanup_failure_both_retained(stage):
    recipe = PythonFunctionRecipe.from_dict(config())
    kwargs = {stage + "_error": RuntimeError("secret candidate source")}
    factory = SandboxFactory(close=RuntimeError("cleanup"), **kwargs)
    result = verifier(factory).verify({"calc.py": "candidate"}, recipe)
    assert {item["category"] for item in result["boundary_failures"]} == {
        "transport_error",
        "retirement_unknown",
    }
    assert not result["retirement"]["retired"]
    assert "secret candidate source" not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.update(schema="unknown"),
        lambda c: c.update(extra=1),
        lambda c: c.update(worker_cases=[]),
        lambda c: c.update(final_cases=[]),
        lambda c: c.update(functions=["__secret"]),
        lambda c: c.update(module_path="absent.py"),
        lambda c: c.update(source_paths=["_cam_bridge.py"]),
        lambda c: c.update(source_paths=["calc.py", "calc.py/sub.py"]),
        lambda c: c["worker_cases"][0].update(function="absent"),
        lambda c: c["worker_cases"][0].update(args=[1.0]),
        lambda c: c["worker_cases"][0].update(kwargs={1: "value"}),
        lambda c: c["worker_cases"][0].update(expect={"error_type": "SystemExit"}),
        lambda c: c["worker_cases"][0].update(expect={}),
        lambda c: c.update(limits={"pids": True}),
        lambda c: c.update(limits={"cpus": True}),
        lambda c: c.update(limits={"cpus": float("nan")}),
        lambda c: c.update(limits={"other": 1}),
        lambda c: c.update(limits={"max_cases": 1}),
        lambda c: c["worker_cases"][0].update(args=["x" * 20000]),
    ],
)
def test_strict_recipe_rejects_unsupported_or_unbounded_config(change):
    trusted = config()
    change(trusted)
    with pytest.raises(ValueError):
        PythonFunctionRecipe.from_dict(trusted)


def test_limits_default_normalization_and_identities_bind_every_effective_limit():
    base = PythonFunctionRecipe.from_dict(config())
    normalized = base.as_dict()
    assert normalized["limits"] == DEFAULT_LIMITS
    assert PythonFunctionRecipe.from_dict(normalized).grader_digest == base.grader_digest
    checker = verifier(SandboxFactory(), base)
    for name, value in normalized["limits"].items():
        changed = copy.deepcopy(normalized)
        changed["limits"][name] = value + (0.1 if name == "cpus" else 1)
        if name in {"max_source_files", "max_source_bytes"}:
            changed["limits"][name] = value - 1
        recipe = PythonFunctionRecipe.from_dict(changed)
        assert recipe.grader_digest != base.grader_digest
        assert checker.environment_for(recipe) != checker.environment_digest


@pytest.mark.parametrize(
    "files",
    [{}, {"calc.py": "candidate", "extra.py": "extra"}, {"calc.py": b"bytes"}, {"calc.py": "x" * 65537}],
)
def test_exact_manifest_and_source_bounds_before_execution(files):
    factory = SandboxFactory()
    with pytest.raises(ValueError):
        verifier(factory).verify(files, PythonFunctionRecipe.from_dict(config()))
    assert factory.instances == []


def test_whole_evaluation_deadline_prevents_provisioning():
    trusted = config()
    trusted["limits"] = {"evaluation_timeout_seconds": 1}
    factory = SandboxFactory()
    result = verifier(factory).verify({"calc.py": "candidate"}, PythonFunctionRecipe.from_dict(trusted))
    assert result["outcome"] == "error"
    assert result["boundary_failures"][0]["category"] == "evaluation_deadline"
    assert factory.instances == []
    assert result["retirement"] == {"retired": True, "instances": []}


def test_production_image_inspection_is_immutable_and_mock_identity_distinct(monkeypatch):
    import service.repair_verification as module

    image = "sha256:" + "a" * 64
    commands = []

    def inspect(argv, **kwargs):
        commands.append(argv)
        return {
            "exit_code": 0,
            "reason": "exited",
            "output": (image + " arm64 linux").encode(),
            "process_group_retired": True,
        }

    monkeypatch.setattr(module, "bounded_process", inspect)
    real = PythonFunctionVerifier(image)
    assert commands[0][:3] == ["docker", "image", "inspect"]
    assert real.environment_digest != verifier(SandboxFactory()).environment_digest
    with pytest.raises(ValueError):
        PythonFunctionVerifier("python:latest")


@pytest.mark.docker
@pytest.mark.parametrize(
    "source,expected",
    [
        ("def add(a,b): return a+b\n", "pass"),
        ("def add(a,b): return a\n", "fail"),
        ("def add(a,b): return 1\n", "fail"),
        ("def add(a,b): print('PASS'); return a+b\n", "error"),
        ("def add(a,b): return True\n", "fail"),
        ("def add(a,b):\n while True: pass\n", "error"),
    ],
)
def test_opt_in_real_docker_controls(source, expected):
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit already present immutable sandbox image required")
    recipe = PythonFunctionRecipe.from_dict(config())
    checker = PythonFunctionVerifier(image, recipe=recipe)
    result = checker.verify({"calc.py": source}, recipe, purpose="final")
    assert result["outcome"] == expected, result
    assert result["retirement"]["retired"] is True
    assert result["tree_digest"] == tree_digest({"calc.py": source})


def test_semantic_failure_does_not_prevent_later_checks_but_cannot_be_overwritten():
    trusted = config()
    trusted["worker_cases"].append({**trusted["worker_cases"][0], "id": "public-two"})
    factory = SandboxFactory([{"value": 2}, {"value": 1}])
    result = verifier(factory).verify({"calc.py": "candidate"}, PythonFunctionRecipe.from_dict(trusted))
    assert result["outcome"] == "fail"
    assert [case["passed"] for case in result["cases"]] == [False, True]
    assert factory.max_live == 1
    assert result["retirement"]["retired"]


def test_uncertain_retirement_preserves_owned_identity_without_diagnostics():
    factory = SandboxFactory(close=RuntimeError("private diagnostic"))
    original = factory.__call__

    def create(image, **kwargs):
        sandbox = original(image, **kwargs)
        sandbox.container_id = "a" * 64
        sandbox.creation_nonce = "b" * 32
        return sandbox

    result = verifier(create).verify({"calc.py": "candidate"}, PythonFunctionRecipe.from_dict(config()))
    evidence = result["retirement"]["instances"][0]
    assert evidence["container_id"] == "a" * 64
    assert evidence["creation_nonce"] == "b" * 32
    assert evidence["retired"] is False
    assert "private diagnostic" not in json.dumps(result)


def test_normalized_bytes_required_and_invalid_phase_rejected():
    trusted = config()
    directly_created = PythonFunctionRecipe(canonical_bytes(trusted))
    checker = verifier(SandboxFactory())
    with pytest.raises(ValueError, match="normalized"):
        checker.verify({"calc.py": "candidate"}, directly_created)
    with pytest.raises(ValueError, match="phase"):
        checker.verify({"calc.py": "candidate"}, PythonFunctionRecipe.from_dict(trusted), purpose="private")


@pytest.mark.parametrize(
    "record",
    [
        {"exit_code": 1, "reason": "exited", "process_group_retired": True},
        {"exit_code": 0, "reason": "timeout", "process_group_retired": True},
        {"exit_code": 0, "reason": "exited", "process_group_retired": False},
    ],
)
def test_image_inspection_incomplete_or_unretired_launcher_rejected(monkeypatch, record):
    import service.repair_verification as module

    image = "sha256:" + "a" * 64
    monkeypatch.setattr(
        module,
        "bounded_process",
        lambda *args, **kwargs: {**record, "output": (image + " arm64 linux").encode()},
    )
    with pytest.raises(ValueError):
        PythonFunctionVerifier(image)


def test_expected_response_envelope_must_fit_output_bound_including_unicode_escaping():
    trusted = config()
    trusted["limits"] = {"max_output_bytes": 256}
    trusted["worker_cases"][0]["expect"]["value"] = "é" * 40
    with pytest.raises(ValueError, match="envelope"):
        PythonFunctionRecipe.from_dict(trusted)
