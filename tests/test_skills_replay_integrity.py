"""Regression for missing original records before and during known replay."""
import pytest
import sqlalchemy as sa

from service.migrations.v2_identity import record_key
from service.storage import TABLES
from test_skills_recovery import REJECT, args, canonical, configure, create_case, sha, snapshot


def delete_original(c, dispatch):
    """Adversarial database intervention, never a supported runtime operation."""
    with c.store._tx() as (connection, _):
        connection.execute(sa.delete(TABLES["dispatches"]).where(
            TABLES["dispatches"].c.id == record_key(c.owner["tenant_id"], dispatch["dispatch_id"])))
        connection.execute(sa.delete(TABLES["receipts"]).where(
            TABLES["receipts"].c.id == sha(canonical([c.owner["tenant_id"], dispatch["receipt_id"]]))))


@pytest.mark.parametrize("kind", ["load_skill", "read_file"])
@pytest.mark.parametrize("cut", ["before_replay", "before_tool_transaction"])
def test_known_checkpoint_cannot_recreate_missing_original_tool(tmp_path, monkeypatch, kind, cut):
    c = create_case(tmp_path)
    arguments = args(c) if kind == "load_skill" else {"path": "a.txt"}
    configure(c, [[("original-tool", kind, arguments)]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    original = next(d for d in snapshot(c)["dispatches"] if d["kind"] == kind)
    observed = {}
    if cut == "before_replay":
        delete_original(c, original)
        observed["after_intervention"] = snapshot(c)
    else:
        begin = c.store._begin_dispatch

        def delete_then_begin(owner, action_id, dispatch_id, dispatch_kind, input_digest, bound_units, **kwargs):
            if dispatch_id == original["dispatch_id"] and "after_intervention" not in observed:
                assert kwargs.get("replay_only") is True
                delete_original(c, original)
                observed["after_intervention"] = snapshot(c)
            return begin(owner, action_id, dispatch_id, dispatch_kind, input_digest, bound_units, **kwargs)

        monkeypatch.setattr(c.store, "_begin_dispatch", delete_then_begin)

    def forbidden(*a, **k):
        pytest.fail("known replay published or sent")

    monkeypatch.setattr(c.artifacts, "put", forbidden)
    monkeypatch.setattr(c.artifacts, "put_json", forbidden)
    monkeypatch.setattr(c.model, "receive", forbidden)
    with pytest.raises(REJECT):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model, pause_after_turn=1)
    assert snapshot(c) == observed["after_intervention"]
    assert all(d["dispatch_id"] != original["dispatch_id"] for d in snapshot(c)["dispatches"])


def test_known_terminal_model_cannot_be_recreated_after_lookup(tmp_path, monkeypatch):
    c = create_case(tmp_path)
    configure(c, [[]])
    c.result = c.harness.run(c.owner, c.task["contract"], c.workspace, c.model)
    original = next(d for d in snapshot(c)["dispatches"] if d["kind"] == "model.nebius")
    begin = c.store._begin_dispatch
    observed = {}

    def delete_then_begin(owner, action_id, dispatch_id, kind, input_digest, bound_units, **kwargs):
        assert dispatch_id == original["dispatch_id"] and kwargs.get("replay_only") is True
        delete_original(c, original)
        observed["after_intervention"] = snapshot(c)
        return begin(owner, action_id, dispatch_id, kind, input_digest, bound_units, **kwargs)

    monkeypatch.setattr(c.store, "_begin_dispatch", delete_then_begin)

    def forbidden(*a, **k):
        pytest.fail("known model replay published or sent")

    monkeypatch.setattr(c.artifacts, "put", forbidden)
    monkeypatch.setattr(c.artifacts, "put_json", forbidden)
    monkeypatch.setattr(c.model, "receive", forbidden)
    with pytest.raises(REJECT, match="reconciliation"):
        c.harness.run(c.owner, c.task["contract"], c.workspace, c.model)
    assert snapshot(c) == observed["after_intervention"]
