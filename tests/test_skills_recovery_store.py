"""R05/R06/R07/R09/R10 transactional controls on SQLite and opt-in PostgreSQL."""
from copy import deepcopy
import os
import uuid

import httpx
import pytest
import sqlalchemy as sa

from service.context import default_context_config
from service.protocol import ToolCall
from test_skills_disclosure import create_case, args, canonical, sha, snapshot
from test_skills_recovery import (
    REJECT, artifact, broker, configure, pause_case, primary,
    receipts, restore, retire_and_reopen, rewrite_row,
)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def backend(request):
    """A fresh schema exercises precisely the same gates on both stores."""
    if request.param == "sqlite":
        yield None
        return
    if not os.environ.get("CAM_TEST_POSTGRES_URL"):
        pytest.skip("CAM_TEST_POSTGRES_URL not configured")
    admin = sa.create_engine(os.environ["CAM_TEST_POSTGRES_URL"])
    namespace = "skills_recovery_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    url = sa.engine.make_url(os.environ["CAM_TEST_POSTGRES_URL"]).update_query_dict(
        {"options": "-csearch_path=" + namespace})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


def unaccepted_cut(path, monkeypatch, url=None):
    """Fully recorded original creator stops immediately before checkpoint API."""
    c = create_case(path, url=url)
    configure(c, [[("load-0", "load_skill", args(c))]])
    candidates = []
    original = c.store.checkpoint
    def stop(owner, manifest):
        candidates.append(deepcopy(manifest))
        raise RuntimeError("test stops before checkpoint admission")
    monkeypatch.setattr(c.store, "checkpoint", stop)
    with pytest.raises(RuntimeError, match="test stops"):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    monkeypatch.setattr(c.store, "checkpoint", original)
    assert len(candidates) == 1 and snapshot(c)["checkpoints"] == []
    return c, candidates[0]


@pytest.mark.parametrize("fault", ["heartbeat", "receipt", "intent", "owner", "seed"])
def test_R05_checkpoint_rechecks_preflight_fingerprint_atomically(tmp_path, monkeypatch, backend, fault):
    c, manifest = unaccepted_cut(tmp_path, monkeypatch, backend)
    original = c.store.read_skill_proof
    after_intervention = []
    def race(owner, **kwargs):
        proof = original(owner, **kwargs)
        if fault == "heartbeat":
            c.store.heartbeat(c.owner, 3600)
        elif fault == "receipt":
            row = next(r for r in receipts(c) if r["dispatch_id"] == primary(c)["load_dispatch_id"])
            rewrite_row(c, "receipts", sha(canonical([c.owner["tenant_id"], row["receipt_id"]])),
                        lambda record: record.update(actual_units=1))
        elif fault == "intent":
            c.store.begin_dispatch(c.owner, "race-action", "race-intent", "read_file", sha(b"race"), 0)
        elif fault == "owner":
            rewrite_row(c, "attempts", c.owner["attempt_id"], lambda record: record.update(lease_until=0))
        else:
            source = next(d for d in snapshot(c)["dispatches"] if d["kind"] == "model.nebius")
            rewrite_row(c, "dispatches", source["dispatch_id"], lambda record:
                record["context_acceptance"]["manifest"].update(source_checkpoint="e" * 64))
        after_intervention.append(snapshot(c))
        return proof
    monkeypatch.setattr(c.store, "read_skill_proof", race)
    with pytest.raises(REJECT):
        c.store.checkpoint(c.owner, manifest)
    assert len(after_intervention) == 1 and snapshot(c) == after_intervention[0]
    assert snapshot(c)["checkpoints"] == []


def test_R05_checkpoint_event_failure_rolls_back_acceptance_and_budget(tmp_path, monkeypatch, backend):
    c, manifest = unaccepted_cut(tmp_path, monkeypatch, backend)
    before = snapshot(c)
    original = c.store._event
    def crash(connection, guard, tenant, task, kind, payload):
        if kind == "checkpoint.accepted":
            raise RuntimeError("checkpoint transaction failure")
        return original(connection, guard, tenant, task, kind, payload)
    monkeypatch.setattr(c.store, "_event", crash)
    with pytest.raises(RuntimeError, match="transaction failure"):
        c.store.checkpoint(c.owner, manifest)
    assert snapshot(c) == before
    monkeypatch.setattr(c.store, "_event", original)
    accepted = c.store.checkpoint(c.owner, manifest)
    before = snapshot(c)
    assert c.store.checkpoint(c.owner, manifest) == accepted and snapshot(c) == before


def test_R09_checkpoint_ack_loss_reuses_exact_authoritative_row(tmp_path, monkeypatch, backend):
    c = create_case(tmp_path, url=backend)
    configure(c, [[("load-0", "load_skill", args(c))]])
    original = c.store.checkpoint
    def lost_ack(owner, manifest):
        original(owner, manifest)
        raise RuntimeError("accepted checkpoint ACK lost")
    monkeypatch.setattr(c.store, "checkpoint", lost_ack)
    with pytest.raises(RuntimeError, match="ACK lost"):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    assert len(snapshot(c)["checkpoints"]) == 1
    before = snapshot(c)
    monkeypatch.setattr(c.store, "checkpoint", original)
    monkeypatch.setattr(c.model, "receive", lambda *a, **k: pytest.fail("ACK replay resent"))
    monkeypatch.setattr(c.artifacts, "put", lambda *a, **k: pytest.fail("ACK replay published"))
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("ACK replay published JSON"))
    result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    assert result["checkpoint_id"] == before["checkpoints"][0]["checkpoint_id"]
    assert result["status"] == "paused" and snapshot(c) == before


def test_R09_known_turn_without_checkpoint_refuses_without_manufacturing_one(tmp_path, monkeypatch, backend):
    c, manifest = unaccepted_cut(tmp_path, monkeypatch, backend)
    assert len(receipts(c)) == 2 and len(primary(c)) == 3
    before = snapshot(c)
    monkeypatch.setattr(c.model, "receive", lambda *a, **k: pytest.fail("known turn resent"))
    monkeypatch.setattr(c.artifacts, "put", lambda *a, **k: pytest.fail("known turn published"))
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("known turn published JSON"))
    with pytest.raises(RuntimeError, match="reconciliation"):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    assert snapshot(c) == before


def test_R09_racing_identical_checkpoint_creator_reuses_exact_committed_row(tmp_path, monkeypatch, backend):
    c, manifest = unaccepted_cut(tmp_path, monkeypatch, backend)
    original = c.store.find_skill_checkpoint
    raced = []
    running = False
    def interleave(owner, context, next_turn, completed):
        nonlocal running
        result = original(owner, context, next_turn, completed)
        if result is None and not running:
            running = True
            accepted = c.store.checkpoint(c.owner, manifest)
            raced.append((accepted, snapshot(c)))
            running = False
        return result
    monkeypatch.setattr(c.store, "find_skill_checkpoint", interleave)
    accepted = c.store.checkpoint(c.owner, manifest)
    assert len(raced) == 1 and accepted == raced[0][0] and snapshot(c) == raced[0][1]


def test_R05_fresh_admission_rechecks_historical_frontier_without_event_change(tmp_path, monkeypatch, backend):
    c = pause_case(tmp_path, url=backend)
    old_owner = deepcopy(c.owner)
    old_model = deepcopy(c.recovery_dispatches[0])
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[]])
    original = c.store._begin_dispatch
    intervened = []
    def race(*arguments, **kwargs):
        if kwargs.get("context_manifest", {}).get("source_checkpoint") == saved["source_checkpoint"]:
            # Adversarial delayed write from historical attempt: no frontier event
            # is changed, so checking just current-owner sequence cannot catch it.
            record = deepcopy(old_model)
            record.update(dispatch_id="late-historical-read", action_id="late-historical-read",
                          kind="read_file", input_digest=sha(b"late historical"),
                          effect_state="in_flight", billing_state="reserved", bound_units=0,
                          result_ref=None, receipt_id=None, actual_units=None)
            record.pop("context_acceptance", None)
            record["parameters"] = {key: record[key] for key in
                ("owner", "action_id", "dispatch_id", "kind", "input_digest", "bound_units")}
            assert record["owner"] == old_owner
            with c.store._tx() as (connection, guard):
                c.store._save(connection, "dispatches", record["dispatch_id"],
                              old_owner["tenant_id"], old_owner["task_id"], record, new=True)
            intervened.append(snapshot(c))
        return original(*arguments, **kwargs)
    monkeypatch.setattr(c.store, "_begin_dispatch", race)
    with pytest.raises(REJECT):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved)
    assert len(intervened) == 1 and snapshot(c) == intervened[0] and not c.recovery_wires


def test_R05_post_checkpoint_known_read_forbids_rewind(tmp_path, backend):
    c = pause_case(tmp_path, url=backend)
    b = broker(c)
    result = b.execute(ToolCall("after-checkpoint-read", "read_file", {"path": "a.txt"}))
    assert result["ok"] is True
    before = snapshot(c)
    with pytest.raises(REJECT):
        restore(c)
    assert snapshot(c) == before


@pytest.mark.parametrize("knowledge", ["in_flight", "unknown_unsettled", "unknown_settled", "known_unsettled", "diagnostic"])
def test_R06_imported_seed_cannot_clear_current_unknown_or_liability(tmp_path, monkeypatch, backend, knowledge):
    c = pause_case(tmp_path, url=backend)
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[]])
    def loss(*a, **k):
        raise httpx.ReadTimeout("local fault after durable intent")
    monkeypatch.setattr(c.model, "receive", loss)
    with pytest.raises(httpx.ReadTimeout):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved)
    d = next(d for d in snapshot(c)["dispatches"] if d["owner"] == c.owner)
    if knowledge == "in_flight":
        rewrite_row(c, "dispatches", d["dispatch_id"], lambda row: row.update(effect_state="in_flight"))
    elif knowledge == "unknown_settled":
        c.store.finish_dispatch(c.owner["tenant_id"], d["dispatch_id"], "trusted-late-bill", "unknown", 1)
    elif knowledge == "known_unsettled":
        rewrite_row(c, "dispatches", d["dispatch_id"], lambda row: row.update(effect_state="succeeded"))
    elif knowledge == "diagnostic":
        ref = c.artifacts.put_json(c.owner["tenant_id"], c.owner["task_id"], {"error": "diagnostic only"})
        ref["content_type"] = "application/vnd.coding-agent.provider-transport-error+json"
        rewrite_row(c, "dispatches", d["dispatch_id"], lambda row: row.update(result_ref=ref))
    before = snapshot(c)
    monkeypatch.setattr(c.artifacts, "put", lambda *a, **k: pytest.fail("Unknown recovery published"))
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("Unknown recovery published JSON"))
    with pytest.raises(REJECT):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved)
    assert snapshot(c) == before
    assert primary(c)["load_dispatch_id"] == saved["skills_state"]["loaded"][0]["load_dispatch_id"]
    if knowledge == "unknown_settled":
        c.store.finish_dispatch(c.owner["tenant_id"], d["dispatch_id"], "trusted-late-bill", "unknown", 1)
        assert snapshot(c) == before


@pytest.mark.parametrize("stage", ["state", "workspace", "payload", "commit"])
def test_R10_checkpoint_failure_keeps_original_load_and_receipt(tmp_path, monkeypatch, backend, stage):
    c = create_case(tmp_path, url=backend)
    configure(c, [[("load-0", "load_skill", args(c))]])
    original = c.artifacts.put_json
    def fault(tenant, task, value):
        is_target = ((stage == "state" and isinstance(value, dict) and value.get("loaded")) or
                     (stage == "workspace" and value == {"a.txt": "unchanged"}) or
                     (stage == "payload" and isinstance(value, dict) and value.get("schema") == 3))
        if is_target:
            raise RuntimeError("local checkpoint publication fault")
        return original(tenant, task, value)
    if stage == "commit":
        monkeypatch.setattr(c.store, "checkpoint", lambda *a, **k:
            (_ for _ in ()).throw(RuntimeError("local checkpoint commit fault")))
    else:
        monkeypatch.setattr(c.artifacts, "put_json", fault)
    with pytest.raises(RuntimeError, match="local checkpoint"):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    load = primary(c)
    rows = snapshot(c)
    assert rows["checkpoints"] == [] and len(c.recovery_wires) == 1
    assert len(receipts(c)) == 2
    d = next(d for d in rows["dispatches"] if d["dispatch_id"] == load["load_dispatch_id"])
    assert d["effect_state"] == "succeeded" and d["billing_state"] == "settled" and d["actual_units"] == 0
    assert artifact(c, d["result_ref"])["value"]["body"]


def test_R07_shared_64_record_exact_boundary_and_two_row_admission_room(tmp_path, backend):
    c = pause_case(tmp_path, url=backend)
    root = primary(c)
    saved = retire_and_reopen(c, tmp_path)
    reads = [("bound-read-" + str(i), "read_file", {"path": "a.txt"}) for i in range(28)]
    configure(c, [reads])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved, pause_after_turn=2)
    proof = c.store.read_skills_checkpoint(c.owner["tenant_id"], c.owner["task_id"], c.result["checkpoint_id"])
    # Independent arithmetic: A model/load receipts4 + A checkpoint1,
    # B model/read receipts58 + B checkpoint1 =64, with no repeated ancestor.
    assert len(proof["dispatches"]) == len(proof["receipts"]) == 31
    assert len(proof["checkpoints"]) == 2 and proof["record_count"] == 64
    assert restore(c)["skills_state"]["loaded"] == [root]
    saved_b = retire_and_reopen(c, tmp_path, "bound-owner-C")
    configure(c, [[]])
    before = snapshot(c)
    with pytest.raises(ValueError) as error:
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved_b)
    assert getattr(error.value, "code", None) == "bounds_exceeded"
    assert snapshot(c) == before and not c.recovery_wires


def test_R07_shared_65th_record_is_rejected_before_proof_is_returned(tmp_path, backend):
    c = pause_case(tmp_path, url=backend)
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[("bound-read-" + str(i), "read_file", {"path": "a.txt"}) for i in range(28)]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved, pause_after_turn=2)
    record = deepcopy(next(d for d in snapshot(c)["dispatches"] if d["owner"] == c.owner and d["kind"] == "read_file"))
    record.update(dispatch_id="injected-sixty-fifth", action_id="injected-sixty-fifth", effect_state="in_flight",
                  billing_state="reserved", result_ref=None, receipt_id=None, actual_units=None)
    record["parameters"] = {key: record[key] for key in
        ("owner", "action_id", "dispatch_id", "kind", "input_digest", "bound_units")}
    with c.store._tx() as (connection, guard):
        c.store._save(connection, "dispatches", record["dispatch_id"], c.owner["tenant_id"],
                      c.owner["task_id"], record, new=True)
    before = snapshot(c)
    with pytest.raises(ValueError) as error:
        c.store.read_skills_checkpoint(c.owner["tenant_id"], c.owner["task_id"], c.result["checkpoint_id"])
    assert getattr(error.value, "code", None) == "bounds_exceeded"
    assert snapshot(c) == before


def test_R07_cycle_rejects_without_recursive_crash_or_new_intent(tmp_path, backend):
    c = pause_case(tmp_path, url=backend)
    identity = c.result["checkpoint_id"]
    rewrite_row(c, "checkpoints", identity, lambda row:
        row["manifest"]["context"]["acceptance"]["manifest"].update(source_checkpoint=identity))
    before = snapshot(c)
    with pytest.raises(REJECT) as error:
        restore(c)
    assert not isinstance(error.value, RecursionError)
    assert snapshot(c) == before


def test_R10_cap_overflow_after_restore_preserves_seed_without_new_model(tmp_path, backend):
    # Q0 fits, captured body makes Q1 exceed the exact frozen request cap.
    c = pause_case(tmp_path, url=backend, body=b"x" * 20000, context=default_context_config(15000))
    saved = retire_and_reopen(c, tmp_path)
    configure(c, [[]])
    before = snapshot(c)
    with pytest.raises(ValueError, match="byte|bound|fit"):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, restored=saved)
    assert snapshot(c) == before and not c.recovery_wires
    assert len(saved["skills_state"]["loaded"]) == 1
    assert "x" * 20000 in saved["messages"][-1]["content"]
