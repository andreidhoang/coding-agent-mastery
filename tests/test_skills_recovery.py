"""Independent frozen R01–R12 recovery oracles, with local HTTP only.

The expected states, transcript and wire records are calculated here; runtime
validators are never used as the oracle. Authoritative-row edits are explicit
adversarial interventions, never a supported recovery operation.
"""
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy as sa

from service.artifacts import LocalArtifacts
from service.contracts import RuntimeErrorBase
from service.execution import Workspace
from service.harness import Harness, ToolBroker
from service.protocol import ToolCall
from service.providers import NebiusChatCompletions, ScriptedModel
from service.recovery import restore_checkpoint
from service.storage import RuntimeStore, TABLES
from test_skills_disclosure import (
    BODY, MODEL, OPAQUE, RESOURCE, args, canonical, create_case, native_response,
    rates, sha, snapshot,
)


REJECT = (ValueError, PermissionError, RuntimeError, RuntimeErrorBase)
PAYLOAD_KEYS = set("schema kind context messages evidence workspace_ref projection_version status skills_after_turn".split())
MANIFEST_KEYS = set("schema kind context artifact_ref workspace_ref provider_artifacts next_turn completion_proposed skills_after_turn".split())


def configure(c, calls, *, max_turns=8, native=True, status=200):
    """Reuse fixture input setup, but independently capture actual outgoing bytes."""
    c.recovery_wires = []
    c.recovery_responses = []
    c.recovery_dispatches = []
    queue = list(calls)

    def transport(request):
        c.recovery_wires.append(bytes(request.content))
        active = [d for d in snapshot(c)["dispatches"] if d["owner"] == c.owner
                  and d["kind"] == "model.nebius" and d["effect_state"] == "in_flight"]
        assert len(active) == 1
        c.recovery_dispatches.append(deepcopy(active[0]))
        raw = native_response(c, queue.pop(0) if queue else [], turn=len(c.recovery_wires))
        # Extra opaque native assistant fields must survive exact continuation.
        raw["choices"][0]["message"]["reasoning_details"] = [
            {"type": "signature", "opaque": "recovery-wire-91e2", "index": 7}]
        c.recovery_responses.append(deepcopy(raw))
        return httpx.Response(status, json=raw)

    c.model = (NebiusChatCompletions("mock-no-paid-call", MODEL, enable_network=True,
        client=httpx.Client(transport=httpx.MockTransport(transport))) if native else
        ScriptedModel([[ToolCall(i, n, a) for i, n, a in batch] for batch in calls]))
    c.harness = Harness(c.store, c.artifacts, max_turns=max_turns, context_config=c.context,
        provider_envelopes={MODEL: rates()} if native else {},
        skills_capture=c.capture, skills_config=c.config)
    return c


def pause_case(path, *, native=True, body=BODY, context=None, url=None):
    c = create_case(path, native=native, body=body, context=context, url=url)
    configure(c, [[("load-0", "load_skill", args(c))]], native=native)
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    return c


def checkpoint(c, checkpoint_id=None):
    identity = checkpoint_id or c.result["checkpoint_id"]
    return next(k for k in snapshot(c)["checkpoints"] if k["checkpoint_id"] == identity)


def artifact(c, ref):
    return c.artifacts.get_json(c.owner["tenant_id"], c.owner["task_id"], ref["digest"])


def receipts(c):
    with c.store._read() as connection:
        return c.store._list(connection, "receipts", c.owner["tenant_id"], c.owner["task_id"])


def restore(c, checkpoint_id=None):
    return restore_checkpoint(c.store, c.artifacts, c.owner["tenant_id"], c.owner["task_id"],
                              checkpoint_id or c.result["checkpoint_id"])


def primary(c):
    d = next(d for d in snapshot(c)["dispatches"] if d["kind"] == "load_skill")
    return {"package_digest": c.package["package_digest"], "load_dispatch_id": d["dispatch_id"],
            "result_ref": d["result_ref"]}


def expected_state(c, loaded, seed=None):
    return {"schema": 1, **deepcopy(c.capture), "loaded": deepcopy(loaded), "source_checkpoint": seed}


def load_result(c):
    d = next(d for d in snapshot(c)["dispatches"] if d["kind"] == "load_skill")
    model = next(row for row in snapshot(c)["dispatches"] if row["dispatch_id"] == d["skill_call"]["source_model_dispatch_id"])
    acceptance = model["context_acceptance"]
    return {"call_id": "load-0", "tool": "load_skill", "ok": True,
        "value": {"schema": 1, "status": "loaded", "catalog_digest": c.capture["catalog_digest"],
            "package_digest": c.package["package_digest"], "body": BODY.decode(), "body_digest": sha(BODY),
            "source_model_dispatch_id": model["dispatch_id"], "resources": [
                {"path": path, "digest": sha(raw), "size": len(raw)}
                for path, raw in sorted(c.package["resources"].items())]},
        "skill_provenance": {"schema": 1, "operation": "load", "catalog_digest": c.capture["catalog_digest"],
            "package_digest": c.package["package_digest"], "path": None,
            "source_model_dispatch_id": model["dispatch_id"], "source_projection_id": acceptance["projection_id"],
            "source_accepted_sequence": acceptance["accepted_sequence"]}}


def retire_and_reopen(c, path, claim="owner-B"):
    old = c.owner
    attempt = next(a for a in snapshot(c)["attempts"] if a["attempt_id"] == old["attempt_id"])
    c.store.retire_sandbox(old["tenant_id"], attempt["sandbox_id"],
        {"exit_observed": True, "supervisor": "trusted-local-recovery-test"})
    url = c.store.engine.url.render_as_string(hide_password=False)
    c.model.client.close() if hasattr(c.model, "client") else None
    c.store.close()
    c.artifacts = LocalArtifacts(path / "artifacts")
    c.store = RuntimeStore(url, c.artifacts)
    restored = restore(c)
    c.owner = c.store.claim(old["tenant_id"], old["task_id"], "node", claim, 90, 3600)["owner"]
    c.workspace = Workspace(path / "workspace", list(restored["files"]))
    return restored


def broker(c):
    return ToolBroker(c.store, c.artifacts, c.owner, c.workspace, c.task["contract"]["capabilities"],
                      skills_capture=c.capture, skills_config=c.config, skills_mode="accepted_skills_v1")


def rewrite_row(c, table, key, change):
    with c.store._tx() as (connection, guard):
        row = c.store._get(connection, table, key, c.owner["tenant_id"], c.owner["task_id"])
        change(row)
        c.store._save(connection, table, key, c.owner["tenant_id"], c.owner["task_id"], row)


def rewrite_checkpoint(c, change):
    k = checkpoint(c)
    payload = artifact(c, k["manifest"]["artifact_ref"])
    change(k["manifest"], payload)
    payload_ref = c.artifacts.put_json(c.owner["tenant_id"], c.owner["task_id"], payload)
    k["manifest"]["artifact_ref"] = payload_ref
    rewrite_row(c, "checkpoints", k["checkpoint_id"], lambda row: row.update(manifest=k["manifest"]))


def test_R01_two_cuts_original_receipts_and_origin_mutation(tmp_path):
    c = pause_case(tmp_path)
    k = checkpoint(c)
    payload = artifact(c, k["manifest"]["artifact_ref"])
    assert c.result["status"] == "paused" and c.result["turns"] == 1
    assert set(k["manifest"]) == MANIFEST_KEYS and set(payload) == PAYLOAD_KEYS
    assert payload["schema"] == 3 and payload["kind"] == "harness_skills_v1"
    assert payload["status"] == "checkpointed" and k["manifest"]["completion_proposed"] is False
    accepted = k["manifest"]["context"]["acceptance"]["manifest"]
    assert artifact(c, accepted["skills_state_ref"]) == expected_state(c, [])
    assert payload["skills_after_turn"] == k["manifest"]["skills_after_turn"]
    assert artifact(c, payload["skills_after_turn"]["state_ref"]) == expected_state(c, [primary(c)])
    original_request = c.artifacts.get(c.owner["tenant_id"], c.owner["task_id"], accepted["request_ref"]["digest"])
    original_receipts = deepcopy(receipts(c))
    original_owner = deepcopy(c.owner)
    result = load_result(c)
    assert artifact(c, primary(c)["result_ref"]) == result
    assert payload["messages"] == [{"role": "user", "content": "Inspect immutable skills"},
        c.recovery_responses[0]["choices"][0]["message"],
        {"role": "tool", "tool_call_id": "load-0", "content": canonical(result).decode()}]
    (c.root / "SKILL.md").write_text("origin removed after capture")
    (c.root / "references/checklist.md").write_text("changed")
    saved = retire_and_reopen(c, tmp_path)
    before = snapshot(c)
    assert restore(c) == saved and snapshot(c) == before
    assert c.artifacts.get(c.owner["tenant_id"], c.owner["task_id"], accepted["request_ref"]["digest"]) == original_request
    configure(c, [[("read-B", "read_skill_resource", args(c, path="references/checklist.md"))]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved, pause_after_turn=2)
    q1 = c.recovery_dispatches[0]
    m = q1["context_acceptance"]["manifest"]
    assert q1["owner"] == c.owner != original_owner
    assert m["binding"]["expected_previous_projection_id"] is None
    assert m["source_checkpoint"] == saved["source_checkpoint"]
    assert m["restored_from_projection_id"] == saved["context"]["acceptance"]["projection_id"]
    assert artifact(c, m["skills_state_ref"]) == expected_state(c, [primary(c)], saved["source_checkpoint"])
    wire = json.loads(c.recovery_wires[0])
    assert wire["messages"][1:] == payload["messages"]
    expected_request = {"provider": "nebius", "protocol": "chat_completions",
        "endpoint": NebiusChatCompletions.ENDPOINT, "payload": wire}
    assert c.artifacts.get(c.owner["tenant_id"], c.owner["task_id"], m["request_ref"]["digest"]) == canonical(expected_request)
    assert sha(canonical(expected_request)) == m["request_digest"] == q1["input_digest"]
    d = next(d for d in snapshot(c)["dispatches"] if d["kind"] == "read_skill_resource")
    read = artifact(c, d["result_ref"])
    assert read["ok"] is True and base64.b64decode(read["value"]["data"]) == RESOURCE[:2]
    assert read["skill_provenance"]["source_model_dispatch_id"] == q1["dispatch_id"]
    assert all(r in receipts(c) for r in original_receipts)


def test_R02_three_owners_preserve_protocol_and_direct_root(tmp_path):
    c = pause_case(tmp_path)
    root = primary(c)
    a_result = deepcopy(c.result)
    seed_a = retire_and_reopen(c, tmp_path)
    configure(c, [[("read-B", "read_skill_resource", args(c, path="references/checklist.md"))]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=seed_a, pause_after_turn=2)
    b_result = deepcopy(c.result)
    seed_b = retire_and_reopen(c, tmp_path, "owner-C")
    configure(c, [[]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=seed_b)
    assert c.result["status"] == "completion_proposed" and c.result["turns"] == 3
    assert len(c.recovery_wires) == 1
    wire = json.loads(c.recovery_wires[0])
    assert wire["messages"][1:] == b_result["messages"]
    assert wire["messages"][2]["reasoning_content"] == OPAQUE
    assert wire["messages"][2]["reasoning_details"] == [{"type": "signature", "opaque": "recovery-wire-91e2", "index": 7}]
    assert seed_b["messages"][:3] == a_result["messages"]
    assert seed_b["evidence"][:1] == a_result["evidence"]
    m = c.recovery_dispatches[0]["context_acceptance"]["manifest"]
    assert artifact(c, m["skills_state_ref"]) == expected_state(c, [root], b_result["checkpoint_id"])
    assert artifact(c, checkpoint(c)["manifest"]["skills_after_turn"]["state_ref"]) == expected_state(c, [root], b_result["checkpoint_id"])


@pytest.mark.parametrize("field", ["messages", "evidence", "files", "skills_state", "skills_after_turn", "context", "next_turn", "completion_proposed"])
def test_R04_submitted_restore_claim_never_bypasses_authoritative_reconstruction(tmp_path, field):
    c = pause_case(tmp_path)
    saved = retire_and_reopen(c, tmp_path)
    changed = deepcopy(saved)
    if field in {"messages", "evidence"}:
        changed[field] = []
    elif field == "next_turn":
        changed[field] = 0
    elif field == "completion_proposed":
        changed[field] = True
    else:
        changed[field] = {}
    configure(c, [[]])
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=changed)
    assert snapshot(c) == before and c.recovery_wires == []


@pytest.mark.parametrize("fault", ["omit_root", "invent_root", "foreign_result", "changed_seed", "extra_state", "two_roots"])
def test_R04_coherent_rehashed_post_state_copies_reject(tmp_path, fault):
    c = pause_case(tmp_path)
    def change(manifest, payload):
        state = artifact(c, manifest["skills_after_turn"]["state_ref"])
        if fault == "omit_root":
            state["loaded"] = []
        elif fault == "invent_root":
            state["loaded"][0]["load_dispatch_id"] = "invented-load"
        elif fault == "foreign_result":
            state["loaded"][0]["result_ref"]["task_id"] = "foreign-task"
        elif fault == "changed_seed":
            state["source_checkpoint"] = "a" * 64
        elif fault == "extra_state":
            state["trusted"] = True
        else:
            state["loaded"].append(deepcopy(state["loaded"][0]))
        ref = c.artifacts.put_json(c.owner["tenant_id"], c.owner["task_id"], state)
        manifest["skills_after_turn"] = payload["skills_after_turn"] = {"state_ref": ref, "state_digest": ref["digest"]}
    rewrite_checkpoint(c, change)
    before = snapshot(c)
    with pytest.raises(REJECT):
        restore(c)
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["body", "tool_call_id", "opaque", "omit_tool", "extra_tool", "evidence"])
def test_R04_rehashed_transcript_cannot_replace_original_protocol_objects(tmp_path, fault):
    c = pause_case(tmp_path)
    def change(manifest, payload):
        if fault == "body":
            value = json.loads(payload["messages"][2]["content"])
            value["value"]["body"] = "invented body"
            value["value"]["body_digest"] = sha(b"invented body")
            payload["messages"][2]["content"] = canonical(value).decode()
        elif fault == "tool_call_id":
            payload["messages"][2]["tool_call_id"] = "wrong-call"
        elif fault == "opaque":
            payload["messages"][1]["reasoning_details"][0]["opaque"] = "replaced"
        elif fault == "omit_tool":
            payload["messages"].pop()
        elif fault == "extra_tool":
            payload["messages"].append(deepcopy(payload["messages"][-1]))
        else:
            payload["evidence"] = []
            manifest["provider_artifacts"] = []
            manifest["next_turn"] = 0
        for key, values in (("checkpoint_history_digest", payload["messages"]), ("checkpoint_evidence_digest", payload["evidence"])):
            manifest["context"][key] = payload["context"][key] = sha(canonical(values))
    rewrite_checkpoint(c, change)
    before = snapshot(c)
    with pytest.raises(REJECT):
        restore(c)
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["missing_receipt", "receipt_owner", "receipt_dispatch", "receipt_result", "dispatch_owner", "source_owner", "source_unknown", "load_unknown", "load_unsettled"])
def test_R04_R06_original_authoritative_rows_are_required(tmp_path, fault):
    c = pause_case(tmp_path)
    rows = snapshot(c)
    load = next(d for d in rows["dispatches"] if d["kind"] == "load_skill")
    source = next(d for d in rows["dispatches"] if d["kind"] == "model.nebius")
    receipt = next(r for r in receipts(c) if r["dispatch_id"] == load["dispatch_id"])
    if fault == "missing_receipt":
        with c.store.engine.begin() as connection:
                connection.execute(sa.delete(TABLES["receipts"]).where(TABLES["receipts"].c.id == sha(canonical([c.owner["tenant_id"], receipt["receipt_id"]]))))
    elif fault.startswith("receipt"):
        def change(row):
            if fault == "receipt_owner":
                row["tenant_id"] = "foreign-tenant"
            elif fault == "receipt_dispatch":
                row["dispatch_id"] = "invented-load"
            else:
                row["result_ref"]["digest"] = "f" * 64
        rewrite_row(c, "receipts", sha(canonical([c.owner["tenant_id"], receipt["receipt_id"]])), change)
    else:
        target = source if fault.startswith("source") else load
        def change(row):
            if fault.endswith("owner"):
                row["owner"]["attempt_id"] = "invented-owner"
            elif fault.endswith("unknown"):
                row["effect_state"] = "unknown"
            else:
                row["billing_state"] = "unsettled"
                row["actual_units"] = None
        rewrite_row(c, "dispatches", target["dispatch_id"], change)
    before = snapshot(c)
    with pytest.raises(REJECT):
        restore(c)
    assert snapshot(c) == before


@pytest.mark.parametrize("schema,kind", [(True, "harness_skills_v1"), (False, "harness_skills_v1"), (4, "harness_skills_v1"), (3, "harness_context_v1"), (3, None)])
def test_R08_explicit_typed_dispatch_rejects_version_or_kind_drift(tmp_path, schema, kind):
    c = pause_case(tmp_path)
    def change(manifest, payload):
        manifest["schema"] = payload["schema"] = schema
        if kind is None:
            manifest.pop("kind")
            payload.pop("kind")
        else:
            manifest["kind"] = payload["kind"] = kind
    rewrite_checkpoint(c, change)
    with pytest.raises(REJECT):
        restore(c)


@pytest.mark.parametrize("fault", ["manifest_extra", "payload_extra", "half_post", "half_context", "bool_turn", "bool_projection"])
def test_R08_closed_typed_checkpoint_boundary(tmp_path, fault):
    c = pause_case(tmp_path)
    def change(manifest, payload):
        if fault == "manifest_extra":
            manifest["trusted"] = True
        elif fault == "payload_extra":
            payload["trusted"] = True
        elif fault == "half_post":
            payload.pop("skills_after_turn")
        elif fault == "half_context":
            manifest.pop("context")
        elif fault == "bool_turn":
            manifest["next_turn"] = True
        else:
            payload["projection_version"] = True
    rewrite_checkpoint(c, change)
    with pytest.raises(REJECT):
        restore(c)


def test_R08_skills_checkpoint_cannot_continue_disabled(tmp_path):
    c = pause_case(tmp_path)
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[]])
    before = snapshot(c)
    with pytest.raises(REJECT):
        Harness(c.store, c.artifacts, context_config=c.context, provider_envelopes={MODEL: rates()}).run(
            c.owner, c.task["contract"], c.workspace, c.model, restored=saved)
    assert snapshot(c) == before and not c.recovery_wires


def test_R09_completed_restore_and_full_known_replay_publish_nothing(tmp_path, monkeypatch):
    c = create_case(tmp_path)
    configure(c, [[("load-0", "load_skill", args(c))], []])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model)
    saved = restore(c)
    assert saved["completion_proposed"] is True
    before = snapshot(c)
    monkeypatch.setattr(c.model, "receive", lambda *a, **k: pytest.fail("known recovery resent"))
    monkeypatch.setattr(c.artifacts, "put", lambda *a, **k: pytest.fail("known recovery published"))
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("known recovery published JSON"))
    assert restore(c) == saved and snapshot(c) == before
    assert c.harness.run(c.owner, c.task["contract"], c.workspace, c.model) == c.result
    assert c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved) == c.result
    assert snapshot(c) == before


def test_R10_exhaustion_has_last_typed_cut_and_cumulative_budget(tmp_path):
    c = create_case(tmp_path)
    configure(c, [[("load-0", "load_skill", args(c))]], max_turns=1)
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model)
    assert c.result["status"] == "turn_budget_exhausted" and c.result["turns"] == 1
    k = checkpoint(c)
    assert artifact(c, k["manifest"]["artifact_ref"])["status"] == "checkpointed"
    assert k["manifest"]["completion_proposed"] is False
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[]], max_turns=1)
    before = snapshot(c)
    result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved)
    assert result["status"] == "turn_budget_exhausted" and result["turns"] == 1
    assert result["checkpoint_id"] == saved["source_checkpoint"]
    assert snapshot(c) == before and not c.recovery_wires


def test_R03_old_receipt_is_data_and_cannot_supply_fresh_resource_authority(tmp_path):
    c = pause_case(tmp_path)
    old_dispatch = c.recovery_dispatches[0]
    saved = retire_and_reopen(c, tmp_path)
    b = broker(c)
    before = snapshot(c)
    with pytest.raises(REJECT):
        b.pin_context(old_dispatch)
    with pytest.raises(REJECT):
        b.execute(ToolCall("read-old-source", "read_skill_resource", args(c, path="references/checklist.md")))
    assert snapshot(c) == before
    assert saved["skills_state"]["loaded"] == [primary(c)]


def test_R03_forged_broker_pin_cannot_use_old_disclosed_resource_source(tmp_path):
    c = create_case(tmp_path)
    configure(c, [[("load-0", "load_skill", args(c))],
        [("read-A", "read_skill_resource", args(c, path="references/checklist.md"))]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=2)
    old_source = next(d for d in snapshot(c)["dispatches"] if d["dispatch_id"] == c.recovery_dispatches[1]["dispatch_id"])
    retire_and_reopen(c, tmp_path)
    b = broker(c)
    # In-memory broker fields are claims too; bypass pin_context in this control.
    b.context_acceptance = deepcopy(old_source["context_acceptance"])
    b.context_dispatch_id = old_source["dispatch_id"]
    b.source_checkpoint = c.result["checkpoint_id"]
    before = snapshot(c)
    with pytest.raises(REJECT):
        b.execute(ToolCall("read-A", "read_skill_resource", args(c, path="references/checklist.md")))
    assert snapshot(c) == before


def test_R02_duplicate_load_in_fresh_owner_points_directly_to_original_primary(tmp_path):
    c = pause_case(tmp_path)
    root = primary(c)
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[("load-B", "load_skill", args(c)), ("load-B2", "load_skill", args(c))]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved, pause_after_turn=2)
    duplicates = [d for d in snapshot(c)["dispatches"] if d["owner"] == c.owner and d["kind"] == "load_skill"]
    assert len(duplicates) == 2
    for d in duplicates:
        value = artifact(c, d["result_ref"])["value"]
        assert value == {"schema": 1, "status": "already_loaded", "catalog_digest": c.capture["catalog_digest"],
            "package_digest": c.package["package_digest"], "load_dispatch_id": root["load_dispatch_id"]}
    assert restore(c)["skills_state"]["loaded"] == [root]


@pytest.mark.parametrize("fault", ["chained", "cycle"])
def test_R07_coherent_duplicate_result_must_point_directly_to_primary(tmp_path, fault):
    c = pause_case(tmp_path)
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[("load-B", "load_skill", args(c)), ("load-B2", "load_skill", args(c))]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved, pause_after_turn=2)
    entries = {artifact(c, d["result_ref"])["call_id"]: d for d in snapshot(c)["dispatches"]
               if d["owner"] == c.owner and d["kind"] == "load_skill"}
    second = entries["load-B2"]
    value = artifact(c, second["result_ref"])
    value["value"]["load_dispatch_id"] = entries["load-B"]["dispatch_id"] if fault == "chained" else second["dispatch_id"]
    ref = c.artifacts.put_json(c.owner["tenant_id"], c.owner["task_id"], value)
    rewrite_row(c, "dispatches", second["dispatch_id"], lambda row: row.update(result_ref=ref))
    rewrite_row(c, "receipts", sha(canonical([c.owner["tenant_id"], second["receipt_id"]])),
                lambda row: row.update(result_ref=ref))
    def change(manifest, payload):
        payload["messages"][-1]["content"] = canonical(value).decode()
        manifest["context"]["checkpoint_history_digest"] = payload["context"]["checkpoint_history_digest"] = sha(canonical(payload["messages"]))
    rewrite_checkpoint(c, change)
    before = snapshot(c)
    with pytest.raises(REJECT) as error:
        restore(c)
    assert not isinstance(error.value, RecursionError) and snapshot(c) == before


@pytest.mark.parametrize("fault", ["request_ref", "result_ref", "call", "owner", "path"])
def test_R04_original_load_identity_cannot_be_coherently_rebound(tmp_path, fault):
    c = pause_case(tmp_path)
    load = next(d for d in snapshot(c)["dispatches"] if d["kind"] == "load_skill")
    def change(row):
        if fault == "request_ref":
            row["skill_call"]["source_model_dispatch_id"] = "foreign-model"
        elif fault == "result_ref":
            ref = c.artifacts.put_json(c.owner["tenant_id"], c.owner["task_id"], {"invented": "load"})
            row["result_ref"] = ref
        elif fault == "call":
            row["input_digest"] = row["parameters"]["input_digest"] = sha(b"wrong call")
        elif fault == "owner":
            row["owner"]["node_epoch"] += 1
            row["parameters"]["owner"] = deepcopy(row["owner"])
        else:
            row["skill_call"]["path"] = "references/invented.md"
    rewrite_row(c, "dispatches", load["dispatch_id"], change)
    before = snapshot(c)
    with pytest.raises(REJECT):
        restore(c)
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["stale_owner", "forged_owner", "missing_configured_caps", "missing_durable_caps", "catalog", "skills_config", "context_config", "adapter"])
def test_R03_changed_authority_or_configuration_rejects_before_send(tmp_path, fault):
    c = pause_case(tmp_path)
    old_owner = deepcopy(c.owner)
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[]])
    if fault == "stale_owner":
        c.owner = old_owner
    elif fault == "forged_owner":
        c.owner = {**c.owner, "node_epoch": c.owner["node_epoch"] + 1}
    elif fault == "missing_configured_caps":
        with pytest.raises(REJECT):
            ToolBroker(c.store, c.artifacts, c.owner, c.workspace, ["load_skill"],
                skills_capture=c.capture, skills_config=c.config, skills_mode="accepted_skills_v1")
        return
    elif fault == "missing_durable_caps":
        rewrite_row(c, "tasks", c.owner["task_id"], lambda row: row["contract"].update(capabilities=["load_skill", "finish"]))
    elif fault == "catalog":
        c.harness.skills_capture["catalog_digest"] = "f" * 64
    elif fault == "skills_config":
        c.harness.skills_config["catalog_version"] = "changed"
    elif fault == "context_config":
        c.harness.context_config["max_bytes"] -= 1
    else:
        c.model.endpoint = "https://invalid.example/forbidden"
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved)
    assert snapshot(c) == before and not c.recovery_wires


def test_R12_unretired_physical_environment_blocks_replacement(tmp_path):
    c = pause_case(tmp_path)
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.store.claim(c.owner["tenant_id"], c.owner["task_id"], "node", "forbidden-replacement", 90, 3600)
    assert snapshot(c) == before


def _subprocess_resume(input_path, output_path):
    """Executed in another interpreter after the source store/client are closed."""
    data = json.loads(Path(input_path).read_text())
    path = Path(data.pop("path"))
    calls = data.pop("calls", [[]])
    claim = data.pop("claim", "process-B")
    pause = data.pop("pause", None)
    retire = data.pop("retire", False)
    c = SimpleNamespace(**data)
    c.artifacts = LocalArtifacts(path / "artifacts")
    c.store = RuntimeStore("sqlite:///" + str(path / "runtime.db"), c.artifacts)
    saved = restore(c)
    c.owner = c.store.claim(c.owner["tenant_id"], c.owner["task_id"], "node", claim, 90, 3600)["owner"]
    c.workspace = Workspace(path / "workspace", list(saved["files"]))
    configure(c, calls)
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved, pause_after_turn=pause)
    if retire:
        attempt = next(a for a in snapshot(c)["attempts"] if a["attempt_id"] == c.owner["attempt_id"])
        c.store.retire_sandbox(c.owner["tenant_id"], attempt["sandbox_id"],
            {"exit_observed": True, "supervisor": "trusted-local-process-test"})
    Path(output_path).write_bytes(canonical({"owner": c.owner, "result": c.result,
        "wire": json.loads(c.recovery_wires[0]), "snapshot": snapshot(c),
        "resume_input": {"path": str(path), "owner": c.owner, "task": c.task,
            "capture": c.capture, "config": c.config, "context": c.context, "result": c.result}}))
    c.model.client.close()
    c.store.close()


def test_R12_clean_interpreter_reopens_persisted_proof_and_native_wire(tmp_path):
    c = pause_case(tmp_path)
    a = deepcopy(c.owner)
    original = deepcopy(c.result)
    attempt = next(a for a in snapshot(c)["attempts"] if a["attempt_id"] == c.owner["attempt_id"])
    c.store.retire_sandbox(c.owner["tenant_id"], attempt["sandbox_id"],
        {"exit_observed": True, "supervisor": "trusted-local-process-test"})
    input_path, output_path = tmp_path / "child-input.json", tmp_path / "child-output.json"
    input_path.write_bytes(canonical({"path": str(tmp_path), "owner": c.owner, "task": c.task,
        "capture": c.capture, "config": c.config, "context": c.context, "result": c.result}))
    c.model.client.close()
    c.store.close()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent) + os.pathsep + str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-c",
        "from test_skills_recovery import _subprocess_resume; import sys; _subprocess_resume(sys.argv[1], sys.argv[2])",
        str(input_path), str(output_path)], env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    resumed = json.loads(output_path.read_text())
    assert resumed["owner"] != a and resumed["result"]["turns"] == 2
    assert resumed["wire"]["messages"][1:] == original["messages"]
    assert resumed["result"]["evidence"][:1] == original["evidence"]
    assert len(resumed["snapshot"]["checkpoints"]) == 2


def test_R12_three_separate_interpreters_preserve_original_root_and_resource(tmp_path):
    c = pause_case(tmp_path)
    a_owner, a_result = deepcopy(c.owner), deepcopy(c.result)
    root = primary(c)
    attempt = next(a for a in snapshot(c)["attempts"] if a["attempt_id"] == c.owner["attempt_id"])
    c.store.retire_sandbox(c.owner["tenant_id"], attempt["sandbox_id"],
        {"exit_observed": True, "supervisor": "trusted-local-process-test"})
    data = {"path": str(tmp_path), "owner": c.owner, "task": c.task,
        "capture": c.capture, "config": c.config, "context": c.context, "result": c.result,
        "claim": "separate-process-B", "pause": 2, "retire": True,
        "calls": [[("read-B", "read_skill_resource", args(c, path="references/checklist.md"))]]}
    c.model.client.close()
    c.store.close()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent) + os.pathsep + str(Path(__file__).resolve().parents[1])
    outputs = []
    for name in ("B", "C"):
        input_path, output_path = tmp_path / (name + "-input.json"), tmp_path / (name + "-output.json")
        input_path.write_bytes(canonical(data))
        completed = subprocess.run([sys.executable, "-c",
            "from test_skills_recovery import _subprocess_resume; import sys; _subprocess_resume(sys.argv[1], sys.argv[2])",
            str(input_path), str(output_path)], env=env, capture_output=True, text=True, timeout=45)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        output = json.loads(output_path.read_text())
        outputs.append(output)
        data = {**output["resume_input"], "claim": "separate-process-C"}
    b, final = outputs
    assert len({a_owner["attempt_id"], b["owner"]["attempt_id"], final["owner"]["attempt_id"]}) == 3
    assert final["result"]["status"] == "completion_proposed" and final["result"]["turns"] == 3
    assert b["wire"]["messages"][1:] == a_result["messages"]
    assert final["wire"]["messages"][1:] == b["result"]["messages"]
    assert final["result"]["evidence"][:1] == a_result["evidence"]
    read = json.loads(final["wire"]["messages"][-1]["content"])
    assert read["call_id"] == "read-B" and base64.b64decode(read["value"]["data"]) == RESOURCE[:2]
    last = next(k for k in final["snapshot"]["checkpoints"] if k["checkpoint_id"] == final["result"]["checkpoint_id"])
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    state = artifacts.get_json(a_owner["tenant_id"], a_owner["task_id"], last["manifest"]["skills_after_turn"]["state_ref"]["digest"])
    assert state == expected_state(c, [root], b["result"]["checkpoint_id"])
