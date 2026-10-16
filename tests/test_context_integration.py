"""Independent boundary tests. All HTTP runs use an in-memory mock transport."""
import base64
import copy
import json

import httpx
import pytest

from service.artifacts import LocalArtifacts, digest_json
from service.billing import ProviderEnvelope
from service.execution import Workspace, materialize, tree_digest
from service.harness import Harness
from service.providers import NebiusChatCompletions
from service.recovery import restore_checkpoint
from service.storage import RuntimeStore

MODEL = "synthetic/NVIDIA-context-fixture"
SENTINEL = "CONTEXT_OLD_TOOL_ONLY_SENTINEL_9ec19"


def rates():
    return {"schema": 1, "unit": "micro_usd", "rate_id": "context-mock", "model": MODEL,
            "input_token_bound": 100, "max_output_tokens": 100,
            "input_per_million": 10000, "output_per_million": 20000,
            "cache_read_per_million": 1000, "cache_write_per_million": 15000,
            "bound_evidence": "synthetic mock only", "max_request_bytes": 65536}


def config():
    return {"schema": 1, "strategy": "tool_result_offload_v1", "max_bytes": 18000,
            "min_offload_bytes": 1024, "keep_recent_tool_batches": 1, "retrieval_max_bytes": 8192}


def native_response(name=None, arguments=None, identity="call"):
    message = {"role": "assistant", "content": None if name else "proposed"}
    if name:
        message["tool_calls"] = [{"id": identity, "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments)}}]
    return {"id": identity, "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "tool_calls" if name else "stop", "message": message}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}


def create_case(path, *, url=None):
    artifacts = LocalArtifacts(path / "artifacts")
    store = RuntimeStore(url or "sqlite:///" + str(path / "runtime.db"), artifacts)
    files = {"old.txt": SENTINEL + "x" * 10000, "recent.txt": "y" * 10000}
    contract = {"repo_id": "fixture", "base_revision": tree_digest(files),
                "requirements": ["Read both files then reload retained context. Propose completion."],
                "model": MODEL, "capabilities": ["read_file", "read_context_artifact", "finish"],
                "rate_snapshot": rates()}
    task = store.submit("context-tenant", "context-key", contract)
    store.set_graph("context-tenant", task["task_id"], 1, [{"node_id": "node"}])
    owner = store.claim("context-tenant", task["task_id"], "node", "claim", 100, 120)["owner"]
    materialize(path / "workspace", files)
    return store, artifacts, task, owner, Workspace(path / "workspace", list(files))


def run_case(path, *, transport_loss=False, url=None, pause_after_turn=None):
    store, artifacts, task, owner, workspace = create_case(path, url=url)
    captured, observed_dispatches, captured_bytes = [], [], []

    def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        captured_bytes.append(bytes(request.content))
        state = store.snapshot(owner["tenant_id"], owner["task_id"])
        dispatch = next(d for d in state["dispatches"] if d["dispatch_id"] == f"model-{owner['attempt_id']}-{len(captured)-1}")
        observed_dispatches.append(copy.deepcopy(dispatch))
        acceptance = dispatch["context_acceptance"]
        manifest = acceptance["manifest"]
        saved = artifacts.get_json(owner["tenant_id"], owner["task_id"], manifest["request_ref"]["digest"])
        assert saved["payload"] == payload
        assert digest_json(saved) == manifest["request_digest"] == dispatch["input_digest"]
        assert acceptance["projection_id"] == digest_json(manifest)
        assert set(dispatch["parameters"]) == {"owner", "action_id", "dispatch_id", "kind", "input_digest", "bound_units"}
        if len(captured) == 1:
            raw = native_response("read_file", {"path": "old.txt"}, "old-read")
            raw["choices"][0]["message"]["reasoning_content"] = "opaque preserved native field"
        elif len(captured) == 2:
            raw = native_response("read_file", {"path": "recent.txt"}, "recent-read")
        elif len(captured) == 3:
            assert SENTINEL not in json.dumps(payload)
            assert manifest["offload_refs"]
            if transport_loss:
                raise httpx.ReadTimeout("lost after accepted projected send")
            raw = native_response("read_context_artifact", {
                "digest": manifest["offload_refs"][0]["digest"], "offset": 0, "limit": 1024}, "reload")
        else:
            raw = native_response()
        return httpx.Response(200, json=raw)

    model = NebiusChatCompletions("mock-never-live", MODEL, enable_network=True,
                                 client=httpx.Client(transport=httpx.MockTransport(handler)))
    harness = Harness(store, artifacts, provider_envelopes={MODEL: rates()}, context_config=config())
    if transport_loss:
        with pytest.raises(httpx.ReadTimeout):
            harness.run(owner, task["contract"], workspace, model)
        result = None
    else:
        result = harness.run(owner, task["contract"], workspace, model, pause_after_turn=pause_after_turn)
    return {"store": store, "artifacts": artifacts, "task": task, "owner": owner,
            "workspace": workspace, "model": model, "harness": harness, "result": result,
            "captured": captured, "captured_bytes": captured_bytes, "observed_dispatches": observed_dispatches}


def test_actual_native_payload_offloads_and_broker_reloads_exact_bytes(tmp_path):
    case = run_case(tmp_path)
    assert len(case["captured"]) == 4
    result = case["result"]
    assert SENTINEL in json.dumps(result["messages"])
    assert result["messages"][1]["reasoning_content"] == "opaque preserved native field"
    third = case["observed_dispatches"][2]["context_acceptance"]
    raw = case["artifacts"].get_json(case["owner"]["tenant_id"], case["owner"]["task_id"], third["manifest"]["raw_history_ref"]["digest"])
    assert SENTINEL in json.dumps(raw)
    state = case["store"].snapshot(case["owner"]["tenant_id"], case["owner"]["task_id"])
    retrieval = next(d for d in state["dispatches"] if d["kind"] == "read_context_artifact")
    assert retrieval["bound_units"] == 0 and retrieval["effect_state"] == "succeeded"
    body = case["artifacts"].get_json(case["owner"]["tenant_id"], case["owner"]["task_id"], retrieval["result_ref"]["digest"])
    assert SENTINEL.encode() in base64.b64decode(body["value"]["bytes_base64"])
    assert body["context_provenance"]["projection_id"] == third["projection_id"]


def test_projected_transport_loss_preserves_unknown_and_once_only_late_settlement(tmp_path):
    case = run_case(tmp_path, transport_loss=True)
    store, owner = case["store"], case["owner"]
    state = store.snapshot(owner["tenant_id"], owner["task_id"])
    last = case["observed_dispatches"][-1]
    dispatch = next(d for d in state["dispatches"] if d["dispatch_id"] == last["dispatch_id"])
    assert dispatch["effect_state"] == "unknown" and dispatch["billing_state"] != "settled"
    assert dispatch["context_acceptance"] == last["context_acceptance"]
    checkpoint = max(state["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    with pytest.raises(ValueError, match="post-checkpoint|reconciliation|unresolved"):
        restore_checkpoint(store, case["artifacts"], owner["tenant_id"], owner["task_id"], checkpoint["checkpoint_id"])
    before = state["budget"]["spent"]
    for _ in range(2):
        store.finish_dispatch(owner["tenant_id"], dispatch["dispatch_id"], "late-context-cost", "unknown", 1)
    state = store.snapshot(owner["tenant_id"], owner["task_id"])
    assert state["budget"]["spent"] == before + 1
    assert next(d for d in state["dispatches"] if d["dispatch_id"] == dispatch["dispatch_id"])["effect_state"] == "unknown"


def next_manifest(case):
    store, artifacts, owner = case["store"], case["artifacts"], case["owner"]
    state = store.snapshot(owner["tenant_id"], owner["task_id"])
    prior = case["observed_dispatches"][-1]["context_acceptance"]
    manifest = copy.deepcopy(prior["manifest"])
    manifest["binding"]["source_frontier"] = state["frontier"]
    manifest["binding"]["expected_previous_projection_id"] = prior["projection_id"]
    projection = artifacts.get_json(owner["tenant_id"], owner["task_id"], manifest["projection_ref"]["digest"])
    projection["binding"] = copy.deepcopy(manifest["binding"])
    manifest["projection_ref"] = artifacts.put_json(owner["tenant_id"], owner["task_id"], projection)
    manifest["projection_digest"] = digest_json(projection)
    return manifest, state["frontier"], prior["projection_id"]


def begin_next(case, manifest, frontier, previous, identity="independent-next"):
    return case["store"].begin_projected_dispatch(
        case["owner"], identity, identity, "model.nebius", manifest["request_digest"], ProviderEnvelope(rates(), MODEL).bound_units,
        projection_manifest=manifest, expected_frontier=frontier,
        expected_previous_projection_id=previous)


def test_accepted_intent_exact_retry_and_atomic_rollback(tmp_path, monkeypatch):
    case = run_case(tmp_path)
    store, owner = case["store"], case["owner"]
    manifest, frontier, previous = next_manifest(case)
    before = store.snapshot(owner["tenant_id"], owner["task_id"])
    original = store._event

    def fail(c, guard, tenant, task, event, payload):
        if event == "context.accepted":
            raise RuntimeError("independent injected transaction crash")
        return original(c, guard, tenant, task, event, payload)

    monkeypatch.setattr(store, "_event", fail)
    with pytest.raises(RuntimeError, match="injected"):
        begin_next(case, manifest, frontier, previous)
    after = store.snapshot(owner["tenant_id"], owner["task_id"])
    assert after == before
    monkeypatch.setattr(store, "_event", original)
    accepted = begin_next(case, manifest, frontier, previous)
    state = store.snapshot(owner["tenant_id"], owner["task_id"])
    duplicate = begin_next(case, manifest, frontier, previous)
    assert duplicate["duplicate"] and duplicate["context_acceptance"] == accepted["context_acceptance"]
    assert store.snapshot(owner["tenant_id"], owner["task_id"]) == state
    changed = copy.deepcopy(manifest)
    changed["request_digest"] = "f" * 64
    with pytest.raises(Exception):
        begin_next(case, changed, frontier, previous)
    assert store.snapshot(owner["tenant_id"], owner["task_id"]) == state
    assert accepted["effect_state"] == "in_flight"


@pytest.mark.parametrize("fault", ["frontier", "previous", "owner", "generation", "contract"])
def test_atomic_publication_refuses_stale_bound_identity(tmp_path, fault):
    case = run_case(tmp_path)
    manifest, frontier, previous = next_manifest(case)
    before = case["store"].snapshot(case["owner"]["tenant_id"], case["owner"]["task_id"])
    if fault == "frontier":
        frontier = {**frontier, "sequence": frontier["sequence"] - 1}
    elif fault == "previous":
        previous = "f" * 64
    else:
        key = {"owner": "owner", "generation": "generation", "contract": "contract_digest"}[fault]
        manifest["binding"][key] = {} if fault == "owner" else (999 if fault == "generation" else "f" * 64)
    with pytest.raises(Exception):
        begin_next(case, manifest, frontier, previous)
    assert case["store"].snapshot(case["owner"]["tenant_id"], case["owner"]["task_id"]) == before


def test_checkpoint_uses_source_prefix_and_preserves_accepted_request_without_planning(tmp_path, monkeypatch):
    case = run_case(tmp_path)
    owner = case["owner"]
    state = case["store"].snapshot(owner["tenant_id"], owner["task_id"])
    checkpoint = max(state["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    last = case["observed_dispatches"][-1]["context_acceptance"]
    source = case["artifacts"].get_json(owner["tenant_id"], owner["task_id"], last["manifest"]["raw_history_ref"]["digest"])
    assert len(case["result"]["messages"]) > len(source["messages"])
    assert case["result"]["messages"][:len(source["messages"])] == source["messages"]
    import service.context as context_module
    monkeypatch.setattr(context_module, "plan_context", lambda *a, **k: (_ for _ in ()).throw(AssertionError("replanned")))
    restored = restore_checkpoint(case["store"], case["artifacts"], owner["tenant_id"], owner["task_id"], checkpoint["checkpoint_id"])
    assert restored["messages"] == case["result"]["messages"]
    assert restored["source_checkpoint"] == checkpoint["checkpoint_id"]
    assert "caller" in restored["authority"]
    assert restored["context"]["acceptance"] == last


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_missing_or_corrupt_projection_artifact_cannot_activate(tmp_path, fault):
    case = run_case(tmp_path)
    manifest, frontier, previous = next_manifest(case)
    owner = case["owner"]
    artifact = case["artifacts"]._path(owner["tenant_id"], owner["task_id"], manifest["projection_ref"]["digest"])
    if fault == "missing":
        artifact.unlink()
    else:
        artifact.write_bytes(b"{}")
    before = case["store"].snapshot(owner["tenant_id"], owner["task_id"])
    with pytest.raises((FileNotFoundError, ValueError)):
        begin_next(case, manifest, frontier, previous)
    assert case["store"].snapshot(owner["tenant_id"], owner["task_id"]) == before


@pytest.mark.postgres
def test_real_postgres_projected_atomicity_and_exact_retry(tmp_path, monkeypatch):
    import os
    import uuid
    import sqlalchemy as sa
    url = os.environ.get("CONTEXT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("explicit local disposable PostgreSQL URL required")
    namespace = "context_independent_" + uuid.uuid4().hex
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    isolated = sa.engine.make_url(url).update_query_dict({"options": "-csearch_path=" + namespace})
    try:
        case = run_case(tmp_path, url=isolated.render_as_string(hide_password=False))
        store, owner = case["store"], case["owner"]
        manifest, frontier, previous = next_manifest(case)
        before = store.snapshot(owner["tenant_id"], owner["task_id"])
        original = store._event

        def crash(c, guard, tenant, task, event, payload):
            if event == "context.accepted":
                raise RuntimeError("independent PostgreSQL rollback probe")
            return original(c, guard, tenant, task, event, payload)

        monkeypatch.setattr(store, "_event", crash)
        with pytest.raises(RuntimeError, match="rollback"):
            begin_next(case, manifest, frontier, previous)
        assert store.snapshot(owner["tenant_id"], owner["task_id"]) == before
        monkeypatch.setattr(store, "_event", original)
        with pytest.raises(Exception):
            begin_next(case, manifest, {**frontier, "sequence": frontier["sequence"] - 1}, previous)
        first = begin_next(case, manifest, frontier, previous)
        committed = store.snapshot(owner["tenant_id"], owner["task_id"])
        second = begin_next(case, manifest, frontier, previous)
        assert second["duplicate"] and second["context_acceptance"] == first["context_acceptance"]
        assert store.snapshot(owner["tenant_id"], owner["task_id"]) == committed
        store.engine.dispose()
    finally:
        with engine.begin() as c:
            c.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        engine.dispose()


def test_broker_current_projection_membership_denies_unrelated_inactive_and_invalid_ranges(tmp_path):
    from service.harness import ToolBroker
    from service.protocol import ToolCall, ProtocolError
    case = run_case(tmp_path)
    owner = case["owner"]
    broker = ToolBroker(case["store"], case["artifacts"], owner, case["workspace"], case["task"]["contract"]["capabilities"])
    current = case["observed_dispatches"][-1]
    broker.pin_context(current)
    refs = current["context_acceptance"]["manifest"]["offload_refs"]
    authorized = refs[0]["digest"]
    unrelated = case["artifacts"].put(owner["tenant_id"], owner["task_id"], b"same task unrelated")
    foreign = case["artifacts"].put(owner["tenant_id"], "foreign-task", b"foreign context")
    args_list = [
        {"digest": unrelated["digest"], "offset": 0, "limit": 8},
        {"digest": foreign["digest"], "offset": 0, "limit": 8},
        {"digest": authorized, "offset": True, "limit": 8},
        {"digest": authorized, "offset": 0, "limit": False},
        {"digest": authorized, "offset": 0, "limit": 8193},
        {"digest": authorized, "offset": refs[0]["size"] + 1, "limit": 8},
    ]
    for index, args in enumerate(args_list):
        if type(args["offset"]) is not int or type(args["limit"]) is not int:
            with pytest.raises(ProtocolError):
                ToolCall("independent-denied-" + str(index), "read_context_artifact", args)
        else:
            result = broker.execute(ToolCall("independent-denied-" + str(index), "read_context_artifact", args))
            assert result["ok"] is False
    broker.pin_context(case["observed_dispatches"][0])
    from service.contracts import Conflict
    before = case["store"].snapshot(owner["tenant_id"], owner["task_id"])
    with pytest.raises(Conflict):
        broker.execute(ToolCall("independent-inactive", "read_context_artifact", {"digest": authorized, "offset": 0, "limit": 8}))
    assert case["store"].snapshot(owner["tenant_id"], owner["task_id"]) == before


def continue_under_fresh_owner(case, path):
    owner = case["owner"]
    old = case["store"]
    snapshot = old.snapshot(owner["tenant_id"], owner["task_id"])
    checkpoint = max(snapshot["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    attempt = next(a for a in snapshot["attempts"] if a["attempt_id"] == owner["attempt_id"])
    old.retire_sandbox(owner["tenant_id"], attempt["sandbox_id"], {"exit_observed": True, "supervisor": "trusted-local-mock"})
    controller = RuntimeStore("sqlite:///" + str(path / "runtime.db"), case["artifacts"])
    restored = restore_checkpoint(controller, case["artifacts"], owner["tenant_id"], owner["task_id"], checkpoint["checkpoint_id"])
    new_owner = controller.claim(owner["tenant_id"], owner["task_id"], "node", "fresh-claim", 90, 120)["owner"]
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        state = controller.snapshot(owner["tenant_id"], owner["task_id"])
        dispatch = next(d for d in state["dispatches"] if d["attempt_id"] == new_owner["attempt_id"] and d["kind"] == "model.nebius")
        manifest = dispatch["context_acceptance"]["manifest"]
        assert manifest["binding"]["owner"] == new_owner
        assert manifest["binding"]["expected_previous_projection_id"] is None
        assert manifest["source_checkpoint"] == checkpoint["checkpoint_id"]
        assert manifest["restored_from_projection_id"] == restored["context"]["acceptance"]["projection_id"]
        saved = case["artifacts"].get_json(owner["tenant_id"], owner["task_id"], manifest["request_ref"]["digest"])
        assert saved["payload"] == payload
        requests.append({"payload": payload, "dispatch": dispatch, "wire_bytes": bytes(request.content)})
        return httpx.Response(200, json=native_response())

    model = NebiusChatCompletions("mock-never-live", MODEL, enable_network=True,
                                 client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = Harness(controller, case["artifacts"], provider_envelopes={MODEL: rates()}, context_config=config()).run(
        new_owner, case["task"]["contract"], case["workspace"], model, restored=restored)
    return controller, restored, result, requests


def test_fresh_controller_owner_resumes_from_raw_prefix_new_chain(tmp_path, monkeypatch):
    case = run_case(tmp_path, pause_after_turn=3)
    assert case["result"]["status"] == "paused"
    import service.harness as harness_module
    calls = []
    planner = harness_module.plan_context

    def observe(contract, messages, evidence, **kwargs):
        calls.append(copy.deepcopy(messages))
        return planner(contract, messages, evidence, **kwargs)

    monkeypatch.setattr(harness_module, "plan_context", observe)
    controller, restored, result, requests = continue_under_fresh_owner(case, tmp_path)
    assert len(requests) == len(calls) == 1
    assert calls[0] == restored["messages"] == case["result"]["messages"]
    assert result["status"] == "completion_proposed"
    assert restored["context"]["acceptance"] == case["observed_dispatches"][-1]["context_acceptance"]
    controller.close()


@pytest.mark.parametrize("fault", ["source_prefix", "schema", "partial_context", "unknown_kind"])
def test_checkpoint_corruption_fails_closed_even_with_rehashed_payload(tmp_path, fault):
    from service.recovery import validate_context_checkpoint
    case = run_case(tmp_path)
    owner, artifacts = case["owner"], case["artifacts"]
    state = case["store"].snapshot(owner["tenant_id"], owner["task_id"])
    checkpoint = max(state["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    manifest = copy.deepcopy(checkpoint["manifest"])
    payload = artifacts.get_json(owner["tenant_id"], owner["task_id"], manifest["artifact_ref"]["digest"])
    if fault == "source_prefix":
        payload["messages"][0]["content"] += " changed raw source"
        payload["context"]["checkpoint_history_digest"] = digest_json(payload["messages"])
        manifest["context"] = copy.deepcopy(payload["context"])
    elif fault == "schema":
        manifest["schema"] = payload["schema"] = 3
    elif fault == "unknown_kind":
        manifest["kind"] = payload["kind"] = "unknown_context_v1"
    else:
        del payload["context"]["source_message_count"]
        manifest["context"] = copy.deepcopy(payload["context"])
    manifest["artifact_ref"] = artifacts.put_json(owner["tenant_id"], owner["task_id"], payload)
    with pytest.raises(ValueError):
        validate_context_checkpoint(artifacts, owner["tenant_id"], owner["task_id"], manifest, payload)


@pytest.mark.parametrize("fault", ["config", "provider", "legacy"])
def test_restore_refuses_config_provider_or_context_mode_drift_without_send(tmp_path, fault):
    case = run_case(tmp_path)
    owner = case["owner"]
    state = case["store"].snapshot(owner["tenant_id"], owner["task_id"])
    checkpoint = max(state["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    restored = restore_checkpoint(case["store"], case["artifacts"], owner["tenant_id"], owner["task_id"], checkpoint["checkpoint_id"])
    selected = config()
    model = case["model"]
    if fault == "config":
        selected["min_offload_bytes"] += 1
    elif fault == "legacy":
        selected = None
    else:
        from service.providers import AnthropicMessages
        model = AnthropicMessages("mock", MODEL, enable_network=True,
                                  client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("sent")))))
        selected["strategy"] = "full_history_v1"
    before = len(case["captured"])
    with pytest.raises(ValueError):
        Harness(case["store"], case["artifacts"], provider_envelopes={MODEL: rates()}, context_config=selected).run(
            owner, case["task"]["contract"], case["workspace"], model, restored=restored)
    assert len(case["captured"]) == before


def test_projected_unknown_remains_extractable_by_existing_failure_evidence(tmp_path):
    from evals.evidence import extract_failure_evidence
    from service.artifacts import digest_bytes
    case = run_case(tmp_path, transport_loss=True)
    owner = case["owner"]
    source = case["store"].capture_failure_source(owner["tenant_id"], owner["task_id"])
    subject = case["observed_dispatches"][-1]["dispatch_id"]
    evidence = extract_failure_evidence(
        source, kind="unknown_dispatch", subject_id=subject,
        window={"start_sequence": 1, "end_sequence": source["capture"]["frontier"]},
        source_provenance={"source_id": "independent-context-test", "origin": "trusted_local_runtime_store",
                           "source_hashes": {"test_context_integration.py": digest_bytes(open(__file__, "rb").read())},
                           "transformations": [], "redactions": []},
        lineage={"family_id": "context-mock-v1", "source_case_id": "projected-lost-response",
                 "parent_evidence_digests": [], "split": "development", "held_out_eligible": False},
        artifact_reader=case["artifacts"].get).verify()
    assert evidence["status"] == "complete", evidence["reasons"]
    assert evidence["subject"]["effect_state"] == "unknown"
    assert next(d for d in evidence["accounting"]["dispatches"] if d["dispatch_id"] == subject)["actual_units"] is None


def test_demo_refuses_existing_directory_without_overwrite(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "preserve.txt").write_bytes(b"retained prior evidence")
    result = subprocess.run([sys.executable, str(root / "scripts" / "context_offloading_demo.py"),
                             "--output", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode != 0
    assert (tmp_path / "preserve.txt").read_bytes() == b"retained prior evidence"
    assert list(tmp_path.iterdir()) == [tmp_path / "preserve.txt"]


@pytest.mark.parametrize("artifact_kind", ["request_ref", "projection_ref", "raw_history_ref", "offload_body"])
def test_recovery_missing_accepted_artifact_fails_before_reconstruction(tmp_path, artifact_kind):
    case = run_case(tmp_path)
    owner = case["owner"]
    snapshot = case["store"].snapshot(owner["tenant_id"], owner["task_id"])
    checkpoint = max(snapshot["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    accepted = checkpoint["manifest"]["context"]["acceptance"]["manifest"]
    ref = accepted["offload_refs"][0]["artifact_ref"] if artifact_kind == "offload_body" else accepted[artifact_kind]
    case["artifacts"]._path(owner["tenant_id"], owner["task_id"], ref["digest"]).unlink()
    with pytest.raises(FileNotFoundError):
        restore_checkpoint(case["store"], case["artifacts"], owner["tenant_id"], owner["task_id"], checkpoint["checkpoint_id"])
