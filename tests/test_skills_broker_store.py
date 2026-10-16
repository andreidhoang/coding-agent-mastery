"""Opt-in, schema-scoped PostgreSQL checks for the new bounded broker SQL path."""
import os
import uuid

import pytest
import sqlalchemy as sa

from service.artifacts import digest_json
from test_skills_broker import (
    REJECTIONS, broker, case, expected_loaded, expected_provenance, generic, load,
    mutate_row, resource, skill_dispatch, snapshot, source, state,
)


pytestmark = [pytest.mark.postgres, pytest.mark.skipif(
    not os.environ.get("CAM_TEST_POSTGRES_URL"), reason="CAM_TEST_POSTGRES_URL not configured")]


@pytest.fixture
def pg_case(tmp_path):
    admin = sa.create_engine(os.environ["CAM_TEST_POSTGRES_URL"])
    namespace = "skills_broker_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    isolated = sa.engine.make_url(os.environ["CAM_TEST_POSTGRES_URL"]).update_query_dict(
        {"options": "-csearch_path=" + namespace})
    c = None
    try:
        c = case(tmp_path, url=isolated.render_as_string(hide_password=False))
        yield c
    finally:
        if c is not None:
            c.store.close()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


def pin(c, calls):
    c.source = source(c, calls)
    c.broker = broker(c)
    c.broker.pin_context(c.source)


def test_postgres_primary_duplicate_and_failed_known_receipts(pg_case):
    c = pg_case
    c.call, read = load(c), resource(c)
    pin(c, [c.call, read])
    expected = expected_loaded(c)
    assert c.broker.execute(c.call) == expected
    before = snapshot(c)
    assert c.broker.execute(c.call) == expected and snapshot(c) == before
    error = c.broker.execute(read)
    assert error["message"] == "not_disclosed" and not error["ok"]
    before = snapshot(c)
    assert c.broker.execute(read) == error and snapshot(c) == before
    records = c.store.read_skill_records(c.owner)
    assert len(records["dispatches"]) == len(records["receipts"]) == 3
    assert len(state(c)["loaded"]) == 1


def test_postgres_exact_cap_and_sql_refusal(pg_case):
    c = pg_case
    c.call = load(c)
    pin(c, [c.call])
    generic(c, 30)
    c.broker.execute(c.call)
    records = c.store.read_skill_records(c.owner)
    assert len(records["dispatches"]) + len(records["receipts"]) == 64
    assert len(state(c)["loaded"]) == 1
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.store.begin_skill_dispatch(c.owner, "over-cap", "over-cap", c.call.digest,
                                     expected_provenance(c, c.call), before["frontier"])
    assert snapshot(c) == before
    c.store.begin_dispatch(c.owner, "ordinary-65", "ordinary-65", "finish", "b" * 64, 0)
    with pytest.raises(REJECTIONS):
        c.store.read_skill_records(c.owner)


def test_postgres_frontier_check_observes_committed_heartbeat(pg_case):
    c = pg_case
    c.call = load(c)
    pin(c, [c.call])
    before = snapshot(c)
    c.store.heartbeat(c.owner, 3600)
    after = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.store.begin_skill_dispatch(c.owner, "stale", "stale", c.call.digest,
                                     expected_provenance(c, c.call), before["frontier"])
    assert snapshot(c) == after and state(c)["loaded"] == []


def test_postgres_receipt_transaction_rollback_keeps_orphan_unloaded(pg_case, monkeypatch):
    c = pg_case
    c.call = load(c)
    pin(c, [c.call])
    original = c.store._event

    def crash(connection, guard, tenant, task, kind, payload):
        if kind == "dispatch.receipt":
            raise RuntimeError("PostgreSQL receipt rollback")
        return original(connection, guard, tenant, task, kind, payload)

    monkeypatch.setattr(c.store, "_event", crash)
    with pytest.raises(RuntimeError, match="rollback"):
        c.broker.execute(c.call)
    dispatch = skill_dispatch(c)
    assert dispatch["effect_state"] == "in_flight" and dispatch["result_ref"] is None
    assert state(c)["loaded"] == []
    records = c.store.read_skill_records(c.owner)
    assert len(records["dispatches"]) == 2 and len(records["receipts"]) == 1
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.broker.execute(c.call)
    assert snapshot(c) == before


def test_postgres_direct_receipt_mismatch_is_not_label_authority(pg_case):
    c = pg_case
    c.call = load(c)
    pin(c, [c.call])
    c.broker.execute(c.call)
    dispatch = skill_dispatch(c)
    mutate_row(c, "receipts", digest_json([c.owner["tenant_id"], dispatch["receipt_id"]]),
               lambda row: row.update(effect_state="unknown"))
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        state(c)
    assert snapshot(c) == before
