"""Frozen stateless function checks; protected assertions never enter candidate sandboxes."""

from __future__ import annotations

import json
import keyword
import math
from pathlib import Path
import re
import time
import uuid
from dataclasses import dataclass

from . import execution as execution_module, protocol as protocol_module
from .artifacts import canonical_bytes, digest_bytes, digest_json
from .execution import DockerSandbox, bounded_process, safe_relative, tree_digest
from .protocol import strict_json

SCHEMA = "python-function-recipe-v1"
DEFAULT_LIMITS = {
    "memory_mb": 192,
    "cpus": 0.5,
    "pids": 32,
    "disk_mb": 16,
    "operation_timeout_seconds": 5,
    "max_output_bytes": 16384,
    "max_request_bytes": 16384,
    "max_cases": 32,
    "max_source_files": 50,
    "max_file_bytes": 65536,
    "max_source_bytes": 262144,
    "evaluation_timeout_seconds": 600,
}
ERROR_TYPES = frozenset(
    {"ValueError", "TypeError", "KeyError", "IndexError", "OverflowError", "RuntimeError"}
)
BRIDGE_PATH = "_cam_bridge.py"
BRIDGE_SOURCE = r"""
import importlib.util, json, sys
request = json.loads(sys.argv[1])
try:
    spec = importlib.util.spec_from_file_location('_cam_candidate', '/workspace/' + request['module'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = vars(module)[request['function']]
    value = function(*request['args'], **request['kwargs'])
    response = {'schema':1,'request_id':request['request_id'],'ok':True,'value':value}
    encoded = json.dumps(response, separators=(',',':'), allow_nan=False)
except Exception as error:
    response = {'schema':1,'request_id':request['request_id'],'ok':False,
                'error_type':type(error).__name__,'message':str(error)[:500]}
    encoded = json.dumps(response, separators=(',',':'), allow_nan=False)
print(encoded)
"""
# Frozen implementation semantics, with source identity added after module load.
POLICY = {
    "schema": 1,
    "comparison": "canonical-json-no-floats-v1",
    "errors": sorted(ERROR_TYPES),
    "case_isolation": "fresh-container-per-stateless-case",
    "bridge": digest_json(BRIDGE_SOURCE),
}
# Existing DockerSandbox launchers have fixed 30-second bounds, plus owned-group
# cleanup grace/reaping. This conservative allowance covers provisioning, recovery,
# duplicate cleanup attempts and final retirement. Admission reserves it BEFORE a
# case; no next case starts without enough remaining whole-evaluation allowance.
CASE_LIFECYCLE_SECONDS = 420


def _keys(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"{label} fields must exactly match schema")


def _identifier(value, label):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise ValueError(f"invalid {label}")
    return value


def _function(value):
    if (
        type(value) is not str
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", value)
        or keyword.iskeyword(value)
    ):
        raise ValueError("unsupported public function identifier")
    return value


def _json_data(value, level=0):
    if level > 20:
        raise ValueError("JSON nesting limit")
    if value is None or type(value) in {str, bool}:
        return
    if type(value) is int:
        if abs(value) > 2**63 - 1:
            raise ValueError("JSON integer outside signed 63-bit magnitude")
        return
    if type(value) is list:
        for item in value:
            _json_data(item, level + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_data(item, level + 1)
        return
    raise ValueError("only null, bool, bounded int, string, list and string-keyed object supported")


def _limits(value):
    if type(value) is not dict or set(value) - set(DEFAULT_LIMITS):
        raise ValueError("unknown limit fields")
    result = {**DEFAULT_LIMITS, **value}
    ranges = {
        "memory_mb": (32, 4096),
        "pids": (4, 256),
        "disk_mb": (1, 128),
        "operation_timeout_seconds": (1, 30),
        "max_output_bytes": (256, 65536),
        "max_request_bytes": (256, 65536),
        "max_cases": (1, 64),
        "max_source_files": (1, 50),
        "max_file_bytes": (1, 262144),
        "max_source_bytes": (1, 262144),
        "evaluation_timeout_seconds": (1, 7200),
    }
    for key, (low, high) in ranges.items():
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f"unsupported {key}")
    if (
        type(result["cpus"]) not in {int, float}
        or not math.isfinite(result["cpus"])
        or not 0 < result["cpus"] <= 4
    ):
        raise ValueError("unsupported cpus")
    result["cpus"] = float(result["cpus"])
    return result


def _source_path(value):
    if type(value) is not str:
        raise ValueError("source path must be text")
    safe_relative(value)
    if (
        value == "."
        or any(part.startswith("_cam_") for part in value.split("/"))
        or len(value.encode()) > 240
    ):
        raise ValueError("reserved or unsupported source path")
    return value


@dataclass(frozen=True)
class PythonFunctionRecipe:
    """Canonical bytes are the only stored state; all projections return fresh copies."""

    _canonical: bytes

    @classmethod
    def from_dict(cls, trusted_config: dict) -> PythonFunctionRecipe:
        if type(trusted_config) is not dict:
            raise ValueError("recipe must be an object")
        _keys(
            trusted_config,
            {"schema", "recipe_id", "source_paths", "module_path", "functions", "worker_cases", "final_cases"}
            | ({"limits"} if "limits" in trusted_config else set()),
            "recipe",
        )
        if trusted_config["schema"] != SCHEMA:
            raise ValueError("unsupported recipe version")
        limits = _limits(trusted_config.get("limits", {}))
        _identifier(trusted_config["recipe_id"], "recipe ID")
        paths = trusted_config["source_paths"]
        if type(paths) is not list or not 1 <= len(paths) <= limits["max_source_files"]:
            raise ValueError("invalid source manifest")
        paths = [_source_path(path) for path in paths]
        if len(set(paths)) != len(paths) or any(p.startswith(q + "/") for p in paths for q in paths):
            raise ValueError("duplicate or conflicting manifest paths")
        module = _source_path(trusted_config["module_path"])
        if module not in paths or not module.endswith(".py"):
            raise ValueError("module must be a declared Python source")
        functions = trusted_config["functions"]
        if type(functions) is not list or not 1 <= len(functions) <= 16:
            raise ValueError("invalid functions allowlist")
        functions = [_function(function) for function in functions]
        if len(set(functions)) != len(functions):
            raise ValueError("duplicate function")
        phases = {}
        for phase in ("worker_cases", "final_cases"):
            cases = trusted_config[phase]
            if type(cases) is not list or not cases or len(cases) > limits["max_cases"]:
                raise ValueError("each phase requires bounded nonempty cases")
            seen = set()
            for case in cases:
                _keys(case, {"id", "function", "args", "kwargs", "expect"}, "case")
                case_id = _identifier(case["id"], "case ID")
                if case_id in seen:
                    raise ValueError("duplicate case ID")
                seen.add(case_id)
                if case["function"] not in functions:
                    raise ValueError("case function not declared")
                if type(case["args"]) is not list or type(case["kwargs"]) is not dict:
                    raise ValueError("arguments must be JSON list/object")
                _json_data(case["args"])
                _json_data(case["kwargs"])
                expect = case["expect"]
                if type(expect) is not dict or set(expect) not in ({"value"}, {"error_type"}):
                    raise ValueError("exactly one assertion required")
                if "value" in expect:
                    _json_data(expect["value"])
                elif type(expect["error_type"]) is not str or expect["error_type"] not in ERROR_TYPES:
                    raise ValueError("unsupported expected exception")
                request = {
                    "schema": 1,
                    "request_id": "0" * 32,
                    "module": module,
                    "function": case["function"],
                    "args": case["args"],
                    "kwargs": case["kwargs"],
                }
                if len(canonical_bytes(request)) > limits["max_request_bytes"]:
                    raise ValueError("case request exceeds bound")
                expected_response = {"schema": 1, "request_id": "0" * 32, "ok": "value" in expect, **expect}
                if "error_type" in expect:
                    expected_response["message"] = ""
                # Bridge output uses ASCII escaping and a trailing print newline.
                output_bytes = (
                    len(json.dumps(expected_response, separators=(",", ":"), allow_nan=False).encode()) + 1
                )
                if output_bytes > limits["max_output_bytes"]:
                    raise ValueError("expectation envelope exceeds output bound")
            phases[phase] = cases
        if sum(map(len, phases.values())) > limits["max_cases"]:
            raise ValueError("total cases exceed bound")
        value = {
            **trusted_config,
            "source_paths": sorted(paths),
            "functions": sorted(functions),
            "limits": limits,
        }
        encoded = canonical_bytes(value)
        if len(encoded) > 524288:
            raise ValueError("recipe byte limit")
        strict_json(encoded.decode(), max_bytes=524288)
        return cls(encoded)

    def as_dict(self) -> dict:
        return json.loads(self._canonical)

    @property
    def grader_digest(self) -> str:
        return digest_json(
            {
                "recipe": self.as_dict(),
                "policy": POLICY,
                "controller": CONTROLLER_DIGEST,
                "dependencies": DEPENDENCY_DIGESTS,
            }
        )

    def public_description(self) -> dict:
        value = self.as_dict()
        del value["final_cases"]
        return value


class PythonFunctionVerifier:
    def __init__(self, image: str, *, sandbox_factory=None, recipe: PythonFunctionRecipe | None = None):
        self._factory = sandbox_factory or DockerSandbox
        self._mock = sandbox_factory is not None
        self.image = image
        if self._mock:
            self._image_identity = {
                "mode": "injected-test-only",
                "image_label": image,
                "factory": f"{getattr(sandbox_factory, '__module__', type(sandbox_factory).__module__)}."
                f"{getattr(sandbox_factory, '__qualname__', type(sandbox_factory).__qualname__)}",
            }
        else:
            if type(image) is not str or not re.fullmatch(
                r"sha256:[0-9a-f]{64}|[^\s]+@sha256:[0-9a-f]{64}", image
            ):
                raise ValueError("already present immutable image required")
            result = bounded_process(
                ["docker", "image", "inspect", image, "--format", "{{.Id}} {{.Architecture}} {{.Os}}"],
                timeout=20,
                max_output=4096,
            )
            if (
                result["exit_code"] != 0
                or result["reason"] != "exited"
                or result.get("process_group_retired") is not True
                or result.get("truncated", False)
            ):
                raise ValueError("immutable image inspection failed")
            parts = result["output"].decode().strip().split()
            if len(parts) != 3 or not re.fullmatch(r"sha256:[0-9a-f]{64}", parts[0]) or parts[2] != "linux":
                raise ValueError("invalid Linux image identity")
            self.image = parts[0]
            self._image_identity = {
                "mode": "linux-container",
                "image_config_id": parts[0],
                "architecture": parts[1],
                "os": parts[2],
            }
        self.environment_digest = self.environment_for(recipe)

    def environment_for(self, recipe: PythonFunctionRecipe | None = None) -> str:
        limits = recipe.as_dict()["limits"] if recipe else _limits({})
        return digest_json(
            {
                "schema": 1,
                **self._image_identity,
                "limits": limits,
                "bridge": digest_json(BRIDGE_SOURCE),
                "controller": CONTROLLER_DIGEST,
                "dependencies": DEPENDENCY_DIGESTS,
                "network": "none",
                "host_mounts": [],
                "uid_gid": "65534:65534",
                "root": "read-only",
                "capabilities": "drop-all",
                "no_new_privileges": True,
                "workspace": "bounded-writable-tmpfs",
                "tmp_mb": 8,
                "workdir": "/workspace",
                "environment": {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp"},
                "nofile": 128,
                "fsize_bytes": 8388608,
                "case_isolation": POLICY["case_isolation"],
                "lifecycle_allowance_seconds": CASE_LIFECYCLE_SECONDS,
                "deadline_policy": "reserve-lifecycle-before-case; stop-on-uncertain-retirement",
            }
        )

    def verify(
        self, files: dict[str, str], recipe: PythonFunctionRecipe, *, purpose="worker", sandbox_id=None, lifecycle=None
    ) -> dict:
        if purpose not in {"worker", "final"}:
            raise ValueError("unsupported verification phase")
        if lifecycle is not None and self._mock:
            raise ValueError("environment journal requires actual Docker backend, not test-only sandbox factory")
        if not isinstance(recipe, PythonFunctionRecipe):
            raise ValueError("frozen recipe required")
        # Reject direct construction of an unvalidated canonical payload.
        validated = PythonFunctionRecipe.from_dict(recipe.as_dict())
        if validated._canonical != recipe._canonical:
            raise ValueError("recipe must contain normalized immutable canonical bytes")
        config = validated.as_dict()
        limits = config["limits"]
        files = dict(files)
        if set(files) != set(config["source_paths"]):
            raise ValueError("candidate manifest must exactly match recipe")
        size = 0
        for path, text in files.items():
            _source_path(path)
            if type(text) is not str:
                raise ValueError("immutable UTF-8 source strings required")
            length = len(text.encode())
            if length > limits["max_file_bytes"]:
                raise ValueError("candidate file byte limit")
            size += length
        if size > limits["max_source_bytes"]:
            raise ValueError("candidate source byte limit")
        verified_digest = tree_digest(files)
        if sandbox_id is not None and (
            type(sandbox_id) is not str or not sandbox_id.isalnum() or not 1 <= len(sandbox_id) <= 64
        ):
            raise ValueError("invalid sandbox reservation identity")
        reservation = sandbox_id or uuid.uuid4().hex
        started = time.monotonic()
        deadline = started + limits["evaluation_timeout_seconds"]
        observations, failures, cases, instances = [], [], [], []
        retired = True
        lifecycle_source = None
        if lifecycle is not None:
            lifecycle_source = lifecycle.source(purpose=purpose, tree_digest=verified_digest,
                input_digest=digest_json({**files, BRIDGE_PATH: BRIDGE_SOURCE}), grader_digest=recipe.grader_digest,
                environment_digest=self.environment_for(recipe))

        def fault(category, ordinal):
            failures.append({"category": category, "case_ordinal": ordinal})

        for ordinal, case in enumerate(config[purpose + "_cases"]):
            # Private configured case IDs can themselves carry sensitive text.
            case_id = case["id"] if purpose == "worker" else f"private-{ordinal + 1}"
            remaining = deadline - time.monotonic()
            allowance = 0 if self._mock else CASE_LIFECYCLE_SECONDS
            if remaining < allowance + limits["operation_timeout_seconds"]:
                fault("evaluation_deadline", ordinal)
                cases.append({"id": case_id, "passed": False, "category": "evaluation_deadline"})
                break
            identity = digest_json({"reservation": reservation, "ordinal": ordinal})[:48]
            request = {
                "schema": 1,
                "request_id": uuid.uuid4().hex,
                "module": config["module_path"],
                "function": case["function"],
                "args": case["args"],
                "kwargs": case["kwargs"],
            }
            category, passed = "transport_error", False
            sandbox = None
            binding = None
            try:
                if lifecycle is not None:
                    from .environment_recovery import launch_value
                    launch = launch_value(self.image, memory_mb=limits["memory_mb"], cpus=limits["cpus"],
                        pids=limits["pids"], disk_mb=limits["disk_mb"], timeout=limits["operation_timeout_seconds"])
                    binding = lifecycle.instance(ordinal=ordinal, source=lifecycle_source, launch=launch,
                                                 max_instances=len(config[purpose + "_cases"]))
                sandbox = self._factory(
                    self.image,
                    memory_mb=limits["memory_mb"],
                    cpus=limits["cpus"],
                    pids=limits["pids"],
                    disk_mb=limits["disk_mb"],
                    timeout=limits["operation_timeout_seconds"],
                    identity=identity,
                    **({"journal_binding": binding} if binding is not None else {}),
                )
                sandbox.start({**files, BRIDGE_PATH: BRIDGE_SOURCE})
                result = sandbox.run(
                    ["python", "-I", "/workspace/" + BRIDGE_PATH, canonical_bytes(request).decode()],
                    max_output=limits["max_output_bytes"],
                )
                category = "process_schema"
                if (
                    type(result) is not dict
                    or type(result.get("exit_code")) is not int
                    or type(result.get("output")) is not str
                    or type(result.get("reason")) is not str
                    or type(result.get("duration_seconds")) not in {int, float}
                    or not math.isfinite(result["duration_seconds"])
                    or result["duration_seconds"] < 0
                ):
                    raise ValueError("invalid process record")
                reason = (
                    result["reason"]
                    if result["reason"] in {"exited", "timeout", "output_limit"}
                    else "unknown"
                )
                observations.append(
                    {
                        "request_id": request["request_id"],
                        "request_digest": digest_json(request),
                        "exit_code": result["exit_code"],
                        "reason": reason,
                        "duration_seconds": result["duration_seconds"],
                        "output_digest": digest_bytes(result["output"].encode()),
                    }
                )
                category = "process_boundary"
                if (
                    result["exit_code"] != 0
                    or reason != "exited"
                    or result.get("truncated", False)
                    or result.get("process_group_retired") is not True
                ):
                    raise ValueError("incomplete process retirement or response")
                category = "response_schema"
                response = strict_json(result["output"], max_bytes=limits["max_output_bytes"])
                if type(response) is not dict or type(response.get("ok")) is not bool:
                    raise ValueError("invalid response")
                expected_keys = {"schema", "request_id", "ok"} | (
                    {"value"} if response["ok"] else {"error_type", "message"}
                )
                _keys(response, expected_keys, "response")
                if (
                    type(response["schema"]) is not int
                    or response["schema"] != 1
                    or response["request_id"] != request["request_id"]
                ):
                    raise ValueError("response identity mismatch")
                if response["ok"]:
                    _json_data(response["value"])
                    passed = "value" in case["expect"] and canonical_bytes(
                        response["value"]
                    ) == canonical_bytes(case["expect"]["value"])
                else:
                    if (
                        type(response["error_type"]) is not str
                        or not 1 <= len(response["error_type"]) <= 80
                        or type(response["message"]) is not str
                        or len(response["message"].encode()) > 2000
                    ):
                        raise ValueError("invalid application exception")
                    passed = response["error_type"] in ERROR_TYPES and response["error_type"] == case[
                        "expect"
                    ].get("error_type")
                category = "pass" if passed else "assertion_mismatch"
            except Exception:
                fault(category, ordinal)
            finally:
                evidence = {"retired": False, "identity": identity}
                if sandbox is not None:
                    try:
                        close = sandbox.close()
                        if type(close) is not dict or close.get("retired") is not True:
                            raise ValueError("retirement not confirmed")
                        # Never echo backend diagnostic strings into final evidence.
                        evidence["retired"] = True
                        for key in ("container_id", "creation_nonce"):
                            value = close.get(key)
                            if type(value) is str and re.fullmatch(r"[0-9a-f]{32}|[0-9a-f]{64}", value):
                                evidence[key] = value
                    except Exception:
                        fault("retirement_unknown", ordinal)
                else:
                    if binding is None:
                        # No journal intent exists and constructor could not create an instance.
                        evidence["retired"] = True
                    else:
                        try:
                            evidence["retired"] = binding.close().get("retired") is True
                        except Exception:
                            fault("retirement_unknown", ordinal)
                if sandbox is not None:
                    for key, attribute in (
                        ("container_id", "container_id"),
                        ("creation_nonce", "creation_nonce"),
                    ):
                        value = getattr(sandbox, attribute, None)
                        if type(value) is str and re.fullmatch(r"[0-9a-f]{32}|[0-9a-f]{64}", value):
                            evidence.setdefault(key, value)
                instances.append(evidence)
                retired = retired and evidence["retired"]
            if time.monotonic() > deadline:
                fault("evaluation_deadline", ordinal)
            if failures:
                passed = False
            cases.append({"id": case_id, "passed": passed, "category": category})
            if not retired or failures:
                break
        selected_count = len(config[purpose + "_cases"])
        passed = (
            not failures
            and retired
            and len(cases) == selected_count
            and all(case["passed"] for case in cases)
        )
        return {
            "schema": 1,
            "recipe_id": config["recipe_id"],
            "phase": purpose,
            "mode": "injected_test_only" if self._mock else "linux_stateless_function_rpc",
            "passed": passed,
            "outcome": "error" if failures else "pass" if passed else "fail",
            "tree_digest": verified_digest,
            "grader_digest": recipe.grader_digest,
            "environment_digest": self.environment_for(recipe),
            "cases": cases,
            "observations": observations,
            "boundary_failures": failures,
            "retirement": {"retired": retired, "instances": instances},
            "limits": limits,
            "elapsed_seconds": time.monotonic() - started,
            "limitations": [
                "single explicitly loaded module; standard library only; no diagnostic printing",
                "stateless JSON functions; no floating-point values",
                "container bounds are not hostile-kernel escape certification",
            ],
        }


# Digest actual controller source so implementation edits invalidate both identities.
CONTROLLER_DIGEST = digest_bytes(Path(__file__).read_bytes())
DEPENDENCY_DIGESTS = {
    "execution": digest_bytes(Path(execution_module.__file__).read_bytes()),
    "protocol": digest_bytes(Path(protocol_module.__file__).read_bytes()),
}
