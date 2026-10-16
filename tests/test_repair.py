"""Repair authority integration with native mock HTTP and strict fixture RPC.

The injected sandbox returns a tiny literal truth table. It never imports,
evaluates, or executes candidate Python in the host process. Real candidate
execution is exercised only by the opt-in immutable Docker-image test.
"""

import copy
import json
import os
import time
from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient

from service.api import Principal, create_app
from service.artifacts import LocalArtifacts, canonical_bytes, digest_bytes, digest_json
from service.billing import ProviderEnvelope
from service.contracts import BudgetExceeded, Fenced, validate_contract
from service.execution import tree_digest
from service.protocol import ProtocolError
from service.repair import RepairEngine
from service.repair_demo import demo_adapter, demo_inputs
from service.repair_provider import ProviderApproval
from service.repair_verification import BRIDGE_PATH, PythonFunctionRecipe, PythonFunctionVerifier
from service.storage import RuntimeStore


TENANT = "repair-integration"
PRIVATE_ID = "private-case-sentinel-63"
PRIVATE_INPUT = "Private Sentinel 63!"
PRIVATE_EXPECTED = "private-sentinel-63"
FIXED_MARKER = 're.findall(r"[a-z0-9]+", text.lower())'


class LiteralSandboxFactory:
    """Bounded fixture behavior, selected solely by known source markers/input."""

    def __init__(self, *, retirement=True):
        self.retirement = retirement
        self.instances = []
        self.live = 0
        self.max_live = 0

    def __call__(self, image, **limits):
        factory = self

        class Sandbox:
            def start(self, files):
                self.files = dict(files)
                self.closed = False
                self.request = None
                self.limits = limits
                factory.live += 1
                factory.max_live = max(factory.max_live, factory.live)

            def run(self, argv, max_output):
                assert argv[:3] == ["python", "-I", "/workspace/" + BRIDGE_PATH]
                self.request = json.loads(argv[3])
                assert set(self.request) == {"schema", "request_id", "module", "function", "args", "kwargs"}
                assert self.request["function"] == "normalize_slug"
                assert self.request["kwargs"] == {}
                source = self.files["slug.py"]
                args = self.request["args"]
                # Only the owned fixture inputs have replies. No source parsing,
                # expected-value access, Python import, eval, exec, or host subprocess.
                fixed = FIXED_MARKER in source
                table = [
                    (["Hello World"], "hello-world"),
                    (["Hello, World!"], "hello-world" if fixed else "hello,-world!"),
                    ([" a\tb  "], "a-b" if fixed else "a\tb"),
                    (["../A_B:42"], "a-b-42" if fixed else "../a_b:42"),
                    ([" ... "], "" if fixed else "..."),
                    ([PRIVATE_INPUT], PRIVATE_EXPECTED if fixed else "wrong-private"),
                ]
                envelope = {"schema": 1, "request_id": self.request["request_id"], "ok": True}
                if args == [7]:
                    envelope = {**envelope, "ok": False, "error_type": "TypeError", "message": ""}
                else:
                    matches = [value for input_args, value in table if input_args == args]
                    assert len(matches) == 1, "unconfigured fixture RPC input"
                    envelope["value"] = matches[0]
                if "PUBLIC_ONLY_FIXTURE" in source and args not in [["Hello World"], ["Hello, World!"]]:
                    envelope = {"schema": 1, "request_id": self.request["request_id"],
                                "ok": True, "value": "wrong-private"}
                return {"output": canonical_bytes(envelope).decode(), "exit_code": 0,
                        "reason": "exited", "duration_seconds": 0.01, "truncated": False,
                        "process_group_retired": True}

            def close(self):
                if factory.retirement and not self.closed:
                    factory.live -= 1
                    self.closed = True
                return {"retired": factory.retirement}

        sandbox = Sandbox()
        self.instances.append(sandbox)
        return sandbox


@dataclass
class Rig:
    store: RuntimeStore
    artifacts: LocalArtifacts
    private: LocalArtifacts
    engine: RepairEngine
    factory: LiteralSandboxFactory
    repository: object
    recipe: PythonFunctionRecipe
    approval: ProviderApproval
    task_id: str
    database: str
    run_root: object

    def snapshot(self):
        return self.store.snapshot(TENANT, self.task_id)

    def reopen(self):
        self.store.close()
        self.store = RuntimeStore(self.database, self.artifacts)
        checker = PythonFunctionVerifier("literal-fixture-only", sandbox_factory=self.factory, recipe=self.recipe)
        self.engine = RepairEngine(self.store, self.artifacts, self.run_root, checker, private_inputs=self.private)


@pytest.fixture
def rig_factory(tmp_path):
    rigs = []

    def make(*, max_turns=12, max_worker_tests=4, positive_rates=False, retirement=True,
             real_image=None, budget_units=None):
        root = tmp_path / str(len(rigs))
        artifacts, private = LocalArtifacts(root / "public"), LocalArtifacts(root / "private")
        database = "sqlite:///" + str(root / "authority.sqlite")
        store = RuntimeStore(database, artifacts)
        repository, recipe, approval, issue = demo_inputs()
        raw = recipe.as_dict()
        raw["final_cases"].append({"id": PRIVATE_ID, "function": "normalize_slug", "args": [PRIVATE_INPUT],
                                   "kwargs": {}, "expect": {"value": PRIVATE_EXPECTED}})
        recipe = PythonFunctionRecipe.from_dict(raw)
        if positive_rates:
            data = approval.as_dict()
            data["rate_snapshot"].update(rate_id="synthetic-positive-ledger-only", input_per_million=1000,
                                         output_per_million=1000)
            approval = ProviderApproval.from_dict(data)
        factory = LiteralSandboxFactory(retirement=retirement)
        checker = (PythonFunctionVerifier(real_image, recipe=recipe) if real_image else
                   PythonFunctionVerifier("literal-fixture-only", sandbox_factory=factory, recipe=recipe))
        engine = RepairEngine(store, artifacts, root / "workspaces", checker, private_inputs=private)
        task = engine.submit(repository, recipe, approval, issue, tenant=TENANT, key="owned-fixture",
                             budget_units=(1000 if positive_rates else 0) if budget_units is None else budget_units,
                             execution_deadline=time.time() + 3600, review_deadline=time.time() + 86400,
                             max_turns=max_turns, max_worker_tests=max_worker_tests)
        rig = Rig(store, artifacts, private, engine, factory, repository, recipe, approval,
                  task["task_id"], database, root / "workspaces")
        rigs.append(rig)
        return rig

    yield make
    for rig in rigs:
        rig.store.close()


def script_adapter(approval, script):
    """Script depends on native history, so restart cannot reset its turn."""
    requests = []

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        turn = sum(m["role"] == "assistant" for m in payload["messages"])
        call = script(turn, payload)
        if isinstance(call, Exception):
            raise call
        if isinstance(call, httpx.Response):
            return call
        name, args = call
        return httpx.Response(200, json={
            "id": f"fixture-response-{turn}", "object": "chat.completion", "model": approval.model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "reasoning_content": f"opaque-native-{turn}",
                "tool_calls": [{"id": f"fixture-call-{turn}", "type": "function", "function": {
                    "name": name, "arguments": json.dumps(args)}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})

    client = httpx.Client(transport=httpx.MockTransport(transport))
    return approval.build_adapter("fixture-only", enable_network=True, client=client), requests


def assert_retired(snapshot):
    assert snapshot["sandboxes"]
    assert all(s["status"] == "retired" and s["retirement_evidence"] for s in snapshot["sandboxes"])


def verifier_results(rig):
    result = []
    for path in (rig.artifacts.root / TENANT / rig.task_id).iterdir():
        value = json.loads(path.read_bytes())
        if isinstance(value, dict) and "phase" in value and "cases" in value:
            result.append(value)
    return result


def test_full_native_repair_current_tree_private_checks_and_completed_no_replay(rig_factory):
    rig = rig_factory(positive_rates=True)
    model, requests = demo_adapter(rig.approval)
    with model.client:
        result = rig.engine.run_task(TENANT, rig.task_id, model)
        assert result["task"]["execution_state"] == "review_eligible"
        assert len(result["reviews"]) == 1 and result["reviews"][0]["status"] == "pending"
        assert len(requests) == 5
        tool_names = [json.loads(m["function"]["arguments"]) for p in requests
                      for m in p["messages"][-2].get("tool_calls", [])
                      if len(p["messages"]) > 2 and p["messages"][-2]["role"] == "assistant"]
        guarded_edit = next(args for args in tool_names if "expected_digest" in args)
        assert guarded_edit["expected_digest"] == digest_bytes(rig.repository.files["slug.py"].encode())
        assert [d["kind"] for d in result["dispatches"]].count("run_tests") == 2
        checks = verifier_results(rig)
        worker = [c for c in checks if c["phase"] == "worker"]
        assert len(worker) == 2
        original = next(c for c in worker if c["tree_digest"] == rig.repository.tree_digest)
        changed = next(c for c in worker if c["tree_digest"] != rig.repository.tree_digest)
        assert not original["passed"] and changed["passed"]
        final = next(c for c in checks if c["phase"] == "final")
        assert final["passed"] and final["tree_digest"] == changed["tree_digest"]
        head = next(c for c in result["candidates"] if c["candidate_id"] == result["task"]["head_candidate_id"])
        assert final["tree_digest"] == tree_digest(head["manifest"]["files"])
        # Before/after worker callbacks received the respective immutable trees.
        sources = [s.files["slug.py"] for s in rig.factory.instances]
        assert sources[:2] == [rig.repository.files["slug.py"]] * 2
        assert all(FIXED_MARKER in source for source in sources[2:])
        assert rig.factory.live == 0 and rig.factory.max_live == 1
        assert_retired(result)
        assert result["budget"]["spent"] == 5 and result["budget"]["reserved"] == 0
        assert all(d["billing_state"] == "settled" for d in result["dispatches"])
        before = rig.snapshot()
        count = len(rig.factory.instances)
        again = rig.engine.run_task(TENANT, rig.task_id)
        assert len(requests) == 5 and len(rig.factory.instances) == count
        assert again["frontier"] == before["frontier"] and again["budget"] == before["budget"]


def test_private_recipe_never_reaches_worker_api_or_public_artifacts(rig_factory):
    rig = rig_factory()
    model, requests = demo_adapter(rig.approval)
    with model.client:
        result = rig.engine.run_task(TENANT, rig.task_id, model)
    for sentinel in (PRIVATE_ID, PRIVATE_INPUT, PRIVATE_EXPECTED):
        assert sentinel not in json.dumps(requests)
        assert sentinel not in json.dumps(result)
        assert all(sentinel.encode() not in path.read_bytes()
                   for path in (rig.artifacts.root / TENANT / rig.task_id).iterdir())
    private_digest = result["task"]["contract"]["repair_spec"]["input_digest"]
    assert PRIVATE_INPUT in json.dumps(rig.private.get_json(TENANT, rig.task_id, private_digest))
    token = "repair-integration-api-token-only"
    app = create_app(rig.store, tokens={token: Principal(TENANT, "reader", frozenset({rig.repository.repo_id}))},
                     artifact_store=rig.artifacts)
    with TestClient(app, headers={"Authorization": "Bearer " + token}) as client:
        for suffix in ("", "/snapshot", "/events?limit=1000"):
            response = client.get(f"/tasks/{rig.task_id}{suffix}")
            assert response.status_code == 200
            assert all(sentinel not in response.text for sentinel in (PRIVATE_ID, PRIVATE_INPUT, PRIVATE_EXPECTED))
        response = client.get(f"/tasks/{rig.task_id}/artifacts/{private_digest}")
        assert response.status_code == 404


@pytest.mark.parametrize("variant", ["unchanged", "public-only"])
def test_unchanged_and_public_only_proposals_fail_independent_final_checks(rig_factory, variant):
    rig = rig_factory()

    def script(turn, payload):
        if variant == "unchanged":
            return "finish", {"summary": "unchanged completion proposal"}
        if turn == 0:
            return "read_file", {"path": "slug.py"}
        if turn == 1:
            old = next(json.loads(m["content"])["value"]["text"] for m in payload["messages"]
                       if m["role"] == "tool")
            return "replace_text", {"path": "slug.py", "expected_digest": digest_bytes(old.encode()),
                                    "old": old, "new": old + "\n# PUBLIC_ONLY_FIXTURE\n# " + FIXED_MARKER}
        if turn == 2:
            return "run_tests", {}
        return "finish", {"summary": "public checks passed; completion proposal"}

    model, requests = script_adapter(rig.approval, script)
    with model.client:
        result = rig.engine.run_task(TENANT, rig.task_id, model)
    assert result["task"]["execution_state"] == "failed"
    assert result["verifications"][0]["outcome"] == "fail"
    assert not result["reviews"]
    checks = verifier_results(rig)
    assert not next(c for c in checks if c["phase"] == "final")["passed"]
    if variant == "public-only":
        assert next(c for c in checks if c["phase"] == "worker")["passed"]
    assert requests and rig.factory.live == 0
    assert_retired(result)


def test_clean_pause_close_reopen_resume_preserves_native_history_and_fences_old_owner(rig_factory):
    rig = rig_factory(positive_rates=True)
    model, first_requests = demo_adapter(rig.approval)
    with model.client:
        paused = rig.engine.run_task(TENANT, rig.task_id, model, pause_after_turn=2)
    assert paused["paused"] and len(first_requests) == 2
    assert_retired(paused)
    old_owner = paused["attempts"][0]["owner"]
    checkpoint = next(c for c in paused["checkpoints"] if c["checkpoint_id"] == paused["checkpoint_id"])
    saved = rig.artifacts.get_json(TENANT, rig.task_id, checkpoint["manifest"]["artifact_ref"]["digest"])
    original_dispatch_ids = {d["dispatch_id"] for d in paused["dispatches"]}
    rig.reopen()
    model, resumed_requests = demo_adapter(rig.approval)
    with model.client:
        finished = rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    assert finished["task"]["execution_state"] == "review_eligible"
    assert len(resumed_requests) == 3
    assert resumed_requests[0]["messages"][1:] == saved["messages"]  # native system is prepended
    new_owner = next(a["owner"] for a in finished["attempts"] if a["owner"] != old_owner)
    assert new_owner["attempt_id"] != old_owner["attempt_id"]
    assert new_owner["node_epoch"] == old_owner["node_epoch"] + 1
    assert original_dispatch_ids <= {d["dispatch_id"] for d in finished["dispatches"]}
    assert sum(d["kind"] == "model.nebius" for d in finished["dispatches"]) == 5
    assert finished["budget"]["spent"] == 5 and finished["budget"]["reserved"] == 0
    with pytest.raises(Fenced):
        rig.store.begin_dispatch(old_owner, "stale-action", "stale-dispatch", "read_file", digest_json({}), 0)
    assert_retired(finished)


def test_turn_limit_is_cumulative_across_clean_resume(rig_factory):
    rig = rig_factory(max_turns=3)
    model, first = demo_adapter(rig.approval)
    with model.client:
        rig.engine.run_task(TENANT, rig.task_id, model, pause_after_turn=2)
    rig.reopen()
    model, second = demo_adapter(rig.approval)
    with model.client, pytest.raises(RuntimeError, match="turn budget exhausted"):
        rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    assert len(first) == 2 and len(second) == 1
    assert sum(d["kind"] == "model.nebius" for d in rig.snapshot()["dispatches"]) == 3
    assert not rig.snapshot()["reviews"]
    assert_retired(rig.snapshot())


def test_worker_test_budget_remains_consumed_across_clean_resume(rig_factory):
    rig = rig_factory(max_worker_tests=1)
    model, first = demo_adapter(rig.approval)
    with model.client:
        paused = rig.engine.run_task(TENANT, rig.task_id, model, pause_after_turn=2)
    old_attempt = paused["attempts"][0]["attempt_id"]
    initial_cases = len(rig.factory.instances)
    rig.reopen()
    model, second = demo_adapter(rig.approval)
    with model.client:
        result = rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    assert len(first) == 2 and len(second) == 3
    tests = [d for d in result["dispatches"] if d["kind"] == "run_tests"]
    assert len(tests) == 2
    original = next(d for d in tests if d["attempt_id"] == old_attempt)
    resumed = next(d for d in tests if d["attempt_id"] != old_attempt)
    assert original["effect_state"] == "succeeded" and resumed["effect_state"] == "failed_known"
    error = rig.artifacts.get_json(TENANT, rig.task_id, resumed["result_ref"]["digest"])
    assert not error["ok"] and "cumulative worker-test limit" in error["message"]
    assert len(rig.factory.instances) == initial_cases + len(rig.recipe.as_dict()["final_cases"])
    assert_retired(result)


def test_positive_request_admission_budget_cannot_reset_across_resume(rig_factory):
    # Synthetic charge is 1 per response and bound is 34 per request. After
    # one settled call, limit 34 leaves 33: the next HTTP request is inadmissible.
    rig = rig_factory(positive_rates=True, budget_units=34)
    assert ProviderEnvelope(rig.approval.rate_snapshot, rig.approval.model).bound_units == 34
    model, first = demo_adapter(rig.approval)
    with model.client:
        paused = rig.engine.run_task(TENANT, rig.task_id, model, pause_after_turn=1)
    assert len(first) == 1 and paused["budget"]["spent"] == 1
    count = len(rig.factory.instances)
    rig.reopen()
    model, resumed = demo_adapter(rig.approval)
    with model.client, pytest.raises(BudgetExceeded):
        rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    assert not resumed and len(rig.factory.instances) == count
    snapshot = rig.snapshot()
    assert snapshot["budget"]["spent"] == 1 and snapshot["budget"]["reserved"] == 0
    assert sum(d["kind"] == "model.nebius" for d in snapshot["dispatches"]) == 1
    assert not snapshot["reviews"]
    assert_retired(snapshot)


def test_model_timeout_after_checkpoint_preserves_bound_and_refuses_replay(rig_factory):
    rig = rig_factory(positive_rates=True)

    def script(turn, payload):
        return ("read_file", {"path": "slug.py"}) if turn == 0 else httpx.ReadTimeout("fixture loss")

    model, requests = script_adapter(rig.approval, script)
    with model.client, pytest.raises(httpx.ReadTimeout):
        rig.engine.run_task(TENANT, rig.task_id, model)
    snapshot = rig.snapshot()
    assert snapshot["checkpoints"] and len(requests) == 2
    unknown = [d for d in snapshot["dispatches"] if d["effect_state"] == "unknown"]
    assert len(unknown) == 1 and unknown[0]["billing_state"] != "settled"
    assert snapshot["budget"]["spent"] == 1
    assert snapshot["budget"]["reserved"] == ProviderEnvelope(rig.approval.rate_snapshot, rig.approval.model).bound_units
    assert_retired(snapshot)
    rig.reopen()
    retry, retry_requests = demo_adapter(rig.approval)
    with retry.client, pytest.raises(RuntimeError, match="unresolved effects"):
        rig.engine.run_task(TENANT, rig.task_id, retry, resume=True)
    assert not retry_requests
    assert rig.snapshot()["budget"] == snapshot["budget"]
    assert not rig.factory.instances


def test_resumed_known_effects_without_checkpoint_cannot_rewind_an_earlier_attempt(rig_factory, monkeypatch):
    rig = rig_factory()
    model, first = demo_adapter(rig.approval)
    with model.client:
        paused = rig.engine.run_task(TENANT, rig.task_id, model, pause_after_turn=2)
    checkpoints = {c["checkpoint_id"] for c in paused["checkpoints"]}
    rig.reopen()

    def fail_checkpoint(*args, **kwargs):
        raise RuntimeError("fixture checkpoint persistence failure")

    monkeypatch.setattr(rig.store, "checkpoint", fail_checkpoint)
    model, second = demo_adapter(rig.approval)
    with model.client, pytest.raises(RuntimeError, match="checkpoint persistence failure"):
        rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    after_effect = rig.snapshot()
    assert len(first) == 2 and len(second) == 1
    assert {c["checkpoint_id"] for c in after_effect["checkpoints"]} == checkpoints
    assert len(after_effect["attempts"]) == 2
    assert all(d["effect_state"] in {"succeeded", "failed_known"} for d in after_effect["dispatches"])
    assert any(d["kind"] == "replace_text" and d["effect_state"] == "succeeded"
               for d in after_effect["dispatches"])
    assert_retired(after_effect)
    count = len(rig.factory.instances)
    rig.reopen()
    model, third = demo_adapter(rig.approval)
    with model.client, pytest.raises((RuntimeError, ValueError), match="post-checkpoint effects"):
        rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    assert not third and len(rig.factory.instances) == count
    assert len(rig.snapshot()["attempts"]) == 2
    assert rig.snapshot()["frontier"] == after_effect["frontier"]


def test_complete_response_with_untrusted_usage_retains_billing_and_blocks_resume(rig_factory):
    rig = rig_factory(positive_rates=True)

    def script(turn, payload):
        if turn == 0:
            return "read_file", {"path": "slug.py"}
        return httpx.Response(200, json={
            "id": "known-response-untrusted-usage", "object": "chat.completion", "model": rig.approval.model,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "proposal with malformed usage"}}],
            "usage": {"prompt_tokens": -1, "completion_tokens": 10, "total_tokens": 9}})

    model, first = script_adapter(rig.approval, script)
    with model.client, pytest.raises((ProtocolError, ValueError)):
        rig.engine.run_task(TENANT, rig.task_id, model)
    snapshot = rig.snapshot()
    assert len(first) == 2 and snapshot["checkpoints"]
    unsettled = [d for d in snapshot["dispatches"] if d["billing_state"] != "settled"]
    assert len(unsettled) == 1 and unsettled[0]["effect_state"] == "succeeded"
    raw_ref = unsettled[0]["result_ref"]
    raw = json.loads(rig.artifacts.get(TENANT, rig.task_id, raw_ref["digest"]))
    assert raw["id"] == "known-response-untrusted-usage"
    assert snapshot["budget"]["reserved"] == ProviderEnvelope(rig.approval.rate_snapshot, rig.approval.model).bound_units
    assert_retired(snapshot)
    rig.reopen()
    model, retry = demo_adapter(rig.approval)
    with model.client, pytest.raises(RuntimeError, match="unresolved billing"):
        rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    assert not retry and not rig.factory.instances
    assert rig.snapshot()["budget"] == snapshot["budget"]


def test_known_final_receipt_survives_publication_crash_without_retesting(rig_factory, monkeypatch):
    rig = rig_factory()

    def fail_publication(*args, **kwargs):
        raise RuntimeError("fixture review publication crash")

    with monkeypatch.context() as patch:
        patch.setattr(rig.store, "publish_review", fail_publication)
        model, first = demo_adapter(rig.approval)
        with model.client, pytest.raises(RuntimeError, match="review publication crash"):
            rig.engine.run_task(TENANT, rig.task_id, model)
    interrupted = rig.snapshot()
    assert len(first) == 5 and len(interrupted["verifications"]) == 1
    assert interrupted["verifications"][0]["outcome"] == "pass" and not interrupted["reviews"]
    count = len(rig.factory.instances)
    assert_retired(interrupted)
    rig.reopen()
    model, requests = demo_adapter(rig.approval)
    with model.client:
        completed = rig.engine.run_task(TENANT, rig.task_id, model, resume=True)
    assert completed["task"]["execution_state"] == "review_eligible"
    assert len(completed["reviews"]) == 1 and completed["reviews"][0]["status"] == "pending"
    assert len(completed["verifications"]) == 1
    assert completed["verifications"] == interrupted["verifications"]
    assert not requests and len(rig.factory.instances) == count
    assert completed["sandboxes"] == interrupted["sandboxes"]


def test_known_failed_final_receipt_survives_terminal_write_crash_without_retesting(rig_factory, monkeypatch):
    rig = rig_factory()

    def fail_terminal_write(*args, **kwargs):
        raise RuntimeError("fixture failure-state write crash")

    with monkeypatch.context() as patch:
        patch.setattr(rig.store, "fail_execution", fail_terminal_write)
        model, requests = script_adapter(rig.approval, lambda turn, payload: (
            "finish", {"summary": "unchanged proposal"}))
        with model.client, pytest.raises(RuntimeError, match="failure-state write crash"):
            rig.engine.run_task(TENANT, rig.task_id, model)
    interrupted = rig.snapshot()
    assert len(requests) == 1 and len(interrupted["verifications"]) == 1
    assert interrupted["verifications"][0]["outcome"] == "fail"
    count = len(rig.factory.instances)
    assert_retired(interrupted)
    rig.reopen()
    finished = rig.engine.run_task(TENANT, rig.task_id, resume=True)
    assert finished["task"]["execution_state"] == "failed" and not finished["reviews"]
    assert finished["verifications"] == interrupted["verifications"]
    assert len(rig.factory.instances) == count
    assert finished["sandboxes"] == interrupted["sandboxes"]


def test_uncertain_test_cleanup_retains_auxiliary_slot_and_refuses_resume(rig_factory):
    rig = rig_factory(retirement=False)
    model, requests = demo_adapter(rig.approval)
    with model.client, pytest.raises(RuntimeError, match="retirement unconfirmed"):
        rig.engine.run_task(TENANT, rig.task_id, model)
    snapshot = rig.snapshot()
    assert len(requests) == 2
    assert len(rig.factory.instances) == 1  # no second case after uncertain cleanup
    retained = [s for s in snapshot["sandboxes"] if s["status"] != "retired"]
    assert len(retained) == 1 and retained[0]["kind"] == "verifier"
    assert all(s["status"] == "retired" for s in snapshot["sandboxes"] if s["kind"] == "patch")
    assert any(d["kind"] == "run_tests" and d["effect_state"] == "unknown" for d in snapshot["dispatches"])
    assert not snapshot["reviews"]
    rig.reopen()
    retry, retry_requests = demo_adapter(rig.approval)
    with retry.client, pytest.raises(RuntimeError, match="retirement requires reconciliation"):
        rig.engine.run_task(TENANT, rig.task_id, retry, resume=True)
    assert not retry_requests and len(rig.factory.instances) == 1


@pytest.mark.parametrize("drift", ["model", "adapter-bound", "environment", "private-input"])
def test_configuration_drift_fails_before_dispatch_or_provisioning(rig_factory, drift, monkeypatch):
    rig = rig_factory()
    model, requests = demo_adapter(rig.approval)
    if drift == "model":
        model.model = "nvidia/different-fixture"
    elif drift == "adapter-bound":
        model.max_bytes += 1
    elif drift == "environment":
        monkeypatch.setattr(rig.engine.verifier, "environment_for", lambda recipe: "a" * 64)
    else:
        spec = rig.snapshot()["task"]["contract"]["repair_spec"]
        rig.private._path(TENANT, rig.task_id, spec["input_digest"]).write_text('{"corrupt":true}')
    with model.client, pytest.raises((ValueError, PermissionError)):
        rig.engine.run_task(TENANT, rig.task_id, model)
    assert not requests and not rig.factory.instances
    assert not rig.snapshot()["attempts"] and not rig.snapshot()["dispatches"]


@pytest.mark.parametrize("mutation", [
    lambda c: c["repair_spec"].update(unknown=1),
    lambda c: c["repair_spec"].pop("provider_digest"),
    lambda c: c["repair_spec"].update(schema=True),
    lambda c: c["repair_spec"].update(max_turns=True),
    lambda c: c["repair_spec"].update(max_turns=0),
    lambda c: c["repair_spec"].update(max_turns=101),
    lambda c: c["repair_spec"].update(max_worker_tests=0),
    lambda c: c["repair_spec"].update(max_worker_tests=9),
    lambda c: c["repair_spec"].update(context_bytes=1023),
    lambda c: c["repair_spec"].update(context_bytes=1048577),
    lambda c: c["repair_spec"].update(input_digest="not-a-digest"),
    lambda c: c.update(repair_spec=[]),
])
def test_task_contract_rejects_invalid_or_unknown_repair_spec(rig_factory, mutation):
    rig = rig_factory()
    contract = copy.deepcopy(rig.snapshot()["task"]["contract"])
    mutation(contract)
    with pytest.raises(ValueError):
        validate_contract(contract)
    with pytest.raises(ValueError):
        rig.store.submit(TENANT, "invalid-contract", contract)


@pytest.mark.docker
def test_opt_in_real_verifier_native_mock_full_repair(rig_factory):
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit already present immutable sandbox image required")
    rig = rig_factory(real_image=image)
    model, requests = demo_adapter(rig.approval)
    with model.client:
        result = rig.engine.run_task(TENANT, rig.task_id, model)
    assert result["task"]["execution_state"] == "review_eligible"
    assert len(requests) == 5 and result["verifications"][0]["outcome"] == "pass"
    assert result["reviews"][0]["status"] == "pending"
    assert not rig.factory.instances
    assert_retired(result)
