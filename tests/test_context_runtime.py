"""Direct authority and typed-recovery adversaries, using local mock HTTP only."""
from copy import deepcopy

import pytest

from service.artifacts import digest_json
from service.billing import ProviderEnvelope
from service.contracts import Conflict
from service.recovery import restore_checkpoint, validate_context_manifest
from test_context_integration import run_case, next_manifest, rates, MODEL


def snapshot(case):
    return case["store"].snapshot(case["owner"]["tenant_id"], case["owner"]["task_id"])


def begin(case, manifest, frontier, previous, *, bound=None, kind="model.nebius"):
    return case["store"].begin_projected_dispatch(
        case["owner"], "runtime-next", "runtime-next", kind, manifest["request_digest"],
        ProviderEnvelope(rates(), MODEL).bound_units if bound is None else bound,
        projection_manifest=manifest, expected_frontier=frontier,
        expected_previous_projection_id=previous,
    )


@pytest.mark.parametrize("fault", ["messages", "model", "tools", "system", "endpoint", "kind", "bound", "stream_integer"])
def test_coherently_hashed_request_forgery_and_underreservation_fail_before_commit(tmp_path, fault):
    case = run_case(tmp_path)
    manifest, frontier, previous = next_manifest(case)
    before = snapshot(case)
    request = case["artifacts"].get_json(case["owner"]["tenant_id"], case["owner"]["task_id"], manifest["request_ref"]["digest"])
    kind, bound = "model.nebius", None
    if fault == "messages":
        request["payload"]["messages"] = [{"role": "user", "content": "forged unrelated request"}]
    elif fault == "model":
        request["payload"]["model"] = "different-model"
    elif fault == "tools":
        request["payload"]["tools"] = []
    elif fault == "system":
        request["payload"]["messages"][0]["content"] = "forged system"
    elif fault == "endpoint":
        request["endpoint"] = "https://unapproved.example/v1"
    elif fault == "kind":
        kind = "model.scripted"
    elif fault == "stream_integer":
        request["payload"]["stream"] = 0
    else:
        bound = 0
    manifest["request_ref"] = case["artifacts"].put_json(case["owner"]["tenant_id"], case["owner"]["task_id"], request)
    manifest["request_digest"] = digest_json(request)
    with pytest.raises((ValueError, Conflict)):
        begin(case, manifest, frontier, previous, kind=kind, bound=bound)
    assert snapshot(case) == before


def test_post_acceptance_insert_failure_rolls_back_event_intent_and_reservation(tmp_path, monkeypatch):
    case = run_case(tmp_path)
    manifest, frontier, previous = next_manifest(case)
    before = snapshot(case)
    original = case["store"]._save

    def fail(c, table, key, tenant, task, value, **kwargs):
        if table == "dispatches" and key == "runtime-next":
            raise RuntimeError("crash after context event insertion")
        return original(c, table, key, tenant, task, value, **kwargs)

    monkeypatch.setattr(case["store"], "_save", fail)
    with pytest.raises(RuntimeError, match="after context"):
        begin(case, manifest, frontier, previous)
    assert snapshot(case) == before
    monkeypatch.setattr(case["store"], "_save", original)
    committed = begin(case, manifest, frontier, previous)
    state = snapshot(case)
    retry = begin(case, manifest, frontier, previous)
    assert retry["duplicate"] and retry["context_acceptance"] == committed["context_acceptance"]
    assert snapshot(case) == state
    assert committed["effect_state"] == "in_flight" and committed["billing_state"] == "reserved"
    with pytest.raises(ValueError, match="reconciliation"):
        restore_checkpoint(case["store"], case["artifacts"], case["owner"]["tenant_id"],
                           case["owner"]["task_id"], case["result"]["checkpoint_id"])


@pytest.mark.parametrize("fault", ["payload_extra", "manifest_extra", "partial_context", "history_prefix", "evidence", "schema_bool", "unknown_kind", "next_negative", "next_bool", "next_string", "next_ahead"])
def test_context_checkpoint_corruption_refuses_authority_publication(tmp_path, fault):
    case = run_case(tmp_path)
    checkpoint = next(c for c in snapshot(case)["checkpoints"] if c["checkpoint_id"] == case["result"]["checkpoint_id"])
    manifest = deepcopy(checkpoint["manifest"])
    payload = case["artifacts"].get_json(case["owner"]["tenant_id"], case["owner"]["task_id"], manifest["artifact_ref"]["digest"])
    if fault == "payload_extra":
        payload["extra"] = 1
    elif fault == "manifest_extra":
        manifest["extra"] = 1
    elif fault == "partial_context":
        del payload["context"]["checkpoint_history_digest"]
        manifest["context"] = deepcopy(payload["context"])
    elif fault == "history_prefix":
        payload["messages"][0]["content"] = "altered raw prefix"
        payload["context"]["checkpoint_history_digest"] = digest_json(payload["messages"])
        manifest["context"] = deepcopy(payload["context"])
    elif fault == "evidence":
        payload["evidence"][0]["response_ref"] = payload["evidence"][0]["request_ref"]
        payload["context"]["checkpoint_evidence_digest"] = digest_json(payload["evidence"])
        manifest["context"] = deepcopy(payload["context"])
        manifest["provider_artifacts"] = deepcopy(payload["evidence"])
    elif fault == "schema_bool":
        payload["schema"] = True
    elif fault == "unknown_kind":
        payload["kind"] = "future_context_v2"
    else:
        manifest["next_turn"] = {"next_negative": -1, "next_bool": True,
                                 "next_string": "four", "next_ahead": len(payload["evidence"]) + 1}[fault]
    manifest["artifact_ref"] = case["artifacts"].put_json(case["owner"]["tenant_id"], case["owner"]["task_id"], payload)
    before = snapshot(case)
    with pytest.raises(ValueError):
        case["store"].checkpoint(case["owner"], manifest)
    assert snapshot(case) == before


def test_same_owner_known_receipt_restart_reuses_accepted_bytes_without_sending(tmp_path, monkeypatch):
    case = run_case(tmp_path)
    monkeypatch.setattr(case["model"], "receive", lambda payload: pytest.fail("known model effect resent"))
    before = snapshot(case)
    result = case["harness"].run(case["owner"], case["task"]["contract"], case["workspace"], case["model"])
    assert result == case["result"]
    assert snapshot(case) == before


def test_schema2_restore_keeps_new_history_and_old_accepted_prefix_distinct(tmp_path):
    case = run_case(tmp_path)
    restored = restore_checkpoint(case["store"], case["artifacts"], case["owner"]["tenant_id"],
                                  case["owner"]["task_id"], case["result"]["checkpoint_id"])
    context = restored["context"]
    source = validate_context_manifest(case["artifacts"], case["owner"]["tenant_id"], case["owner"]["task_id"],
                                       context["acceptance"]["manifest"])["source"]
    assert len(restored["messages"]) > context["source_message_count"]
    assert restored["messages"][:context["source_message_count"]] == source["messages"]
    assert "grants none" in restored["authority"]



def test_stale_broker_pin_cannot_create_new_retrieval_but_exact_receipt_can_be_reused(tmp_path):
    from service.harness import ToolBroker
    from service.protocol import ToolCall
    case = run_case(tmp_path)
    broker = ToolBroker(case["store"], case["artifacts"], case["owner"], case["workspace"],
                        case["task"]["contract"]["capabilities"])
    third = case["observed_dispatches"][2]
    broker.pin_context(third)
    digest = third["context_acceptance"]["manifest"]["offload_refs"][0]["digest"]
    before = snapshot(case)
    with pytest.raises(Conflict, match="latest accepted"):
        broker.execute(ToolCall("runtime-stale", "read_context_artifact", {"digest": digest, "offset": 0, "limit": 8}))
    assert snapshot(case) == before
    # Same logical call under its original projection is a durable result read,
    # despite the later projection; there is no second artifact effect or intent.
    result = broker.execute(ToolCall("reload", "read_context_artifact", {"digest": digest, "offset": 0, "limit": 1024}))
    assert result["ok"] and result["context_provenance"]["projection_id"] == third["context_acceptance"]["projection_id"]
    assert snapshot(case) == before



@pytest.mark.parametrize("tagged", [False, True])
def test_historical_minimal_legacy_checkpoint_restores_without_context_upgrade(tmp_path, tagged):
    from test_context_integration import create_case
    case_store, artifacts, task, owner, workspace = create_case(tmp_path)
    workspace_ref = artifacts.put_json(owner["tenant_id"], owner["task_id"], workspace.snapshot())
    payload = {"messages": [], "evidence": [], "workspace_ref": workspace_ref}
    if tagged:
        payload["schema"] = 1
    payload_ref = artifacts.put_json(owner["tenant_id"], owner["task_id"], payload)
    checkpoint = case_store.checkpoint(owner, {"artifact_ref": payload_ref, "next_turn": 0})
    restored = restore_checkpoint(case_store, artifacts, owner["tenant_id"], owner["task_id"], checkpoint["checkpoint_id"])
    assert restored["next_turn"] == 0 and restored["messages"] == [] and "context" not in restored
    assert restored["files"] == workspace.snapshot()
    from service.harness import Harness
    from service.providers import ScriptedModel
    from service.context import default_context_config
    with pytest.raises(ValueError, match="legacy checkpoint cannot restore context"):
        Harness(case_store, artifacts, context_config=default_context_config()).run(
            owner, task["contract"], workspace, ScriptedModel([]), restored=restored,
        )


@pytest.mark.parametrize("marker,value", [("kind", "harness_context_v1"), ("context", {}),
                                          ("context_schema", 1), ("schema", 2),
                                          ("schema", 999), ("schema", True)])
def test_legacy_shaped_payload_with_explicit_context_marker_never_downgrades(tmp_path, marker, value):
    from test_context_integration import create_case
    case_store, artifacts, _, owner, workspace = create_case(tmp_path)
    workspace_ref = artifacts.put_json(owner["tenant_id"], owner["task_id"], workspace.snapshot())
    payload = {"messages": [], "evidence": [], "workspace_ref": workspace_ref, marker: value}
    payload_ref = artifacts.put_json(owner["tenant_id"], owner["task_id"], payload)
    checkpoint = case_store.checkpoint(owner, {"artifact_ref": payload_ref, "next_turn": 0})
    with pytest.raises(ValueError, match="closed context checkpoint"):
        restore_checkpoint(case_store, artifacts, owner["tenant_id"], owner["task_id"], checkpoint["checkpoint_id"])
