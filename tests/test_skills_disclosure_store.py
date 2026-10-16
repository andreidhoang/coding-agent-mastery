"""Opt-in real PostgreSQL evidence for v2 bounded reads and atomic admission."""
import os
import uuid

import pytest
import sqlalchemy as sa

from test_skills_broker import generic
from test_skills_disclosure import (
    REJECTIONS, begin, complete_fixture_model, next_candidate, run_case, skills_state, snapshot,
)


pytestmark = [pytest.mark.postgres, pytest.mark.skipif(
    not os.environ.get("CAM_TEST_POSTGRES_URL"), reason="CAM_TEST_POSTGRES_URL not configured")]


@pytest.fixture
def pg_case(tmp_path):
    admin = sa.create_engine(os.environ["CAM_TEST_POSTGRES_URL"])
    namespace = "skills_disclosure_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    url = sa.engine.make_url(os.environ["CAM_TEST_POSTGRES_URL"]).update_query_dict(
        {"options": "-csearch_path=" + namespace})
    c = None
    try:
        c = run_case(tmp_path, url=url.render_as_string(hide_password=False))
        yield c
    finally:
        if c is not None:
            c.store.close()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


def test_postgres_actual_mock_send_and_loaded_state(pg_case):
    c = pg_case
    assert len(c.captured) == 3 and len(skills_state(c)["loaded"]) == 1
    records = c.store.read_skill_records(c.owner)
    assert len(records["dispatches"]) == len(records["receipts"]) == 6
    assert {d["effect_state"] for d in records["dispatches"]} == {"succeeded", "failed_known"}
    assert len(snapshot(c)["checkpoints"]) == 3
    assert all(k["manifest"]["schema"] == 3 for k in snapshot(c)["checkpoints"])


def test_postgres_historical_exact_replay_does_not_publish_send_or_charge(pg_case, monkeypatch):
    c = pg_case
    before = snapshot(c)
    monkeypatch.setattr(c.model, "receive", lambda *a: pytest.fail("PostgreSQL replay sent"))
    monkeypatch.setattr(c.artifacts, "put", lambda *a, **k: pytest.fail("PostgreSQL replay published"))
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("PostgreSQL replay published"))
    assert c.harness.run(c.owner, c.task["contract"], c.workspace, c.model) == c.result
    assert snapshot(c) == before


def test_postgres_acceptance_event_intent_and_reservation_rollback(pg_case, monkeypatch):
    c = pg_case
    manifest = next_candidate(c)
    before = snapshot(c)
    original = c.store._event
    def crash(connection, guard, tenant, task, kind, payload):
        if kind == "context.accepted":
            raise RuntimeError("PostgreSQL atomic rollback")
        return original(connection, guard, tenant, task, kind, payload)
    monkeypatch.setattr(c.store, "_event", crash)
    with pytest.raises(RuntimeError, match="rollback"):
        begin(c, manifest)
    assert snapshot(c) == before
    monkeypatch.setattr(c.store, "_event", original)
    accepted = begin(c, manifest)
    before = snapshot(c)
    assert accepted["effect_state"] == "in_flight" and begin(c, manifest)["duplicate"]
    assert snapshot(c) == before


def test_postgres_model_slot_bound_and_frontier(pg_case):
    c = pg_case
    stale = next_candidate(c)
    c.store.heartbeat(c.owner, 3600)
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        begin(c, stale, "stale")
    assert snapshot(c) == before
    generic(c, 25)
    manifest = next_candidate(c)
    accepted = begin(c, manifest)
    complete_fixture_model(c, accepted)
    records = c.store.read_skill_records(c.owner)
    assert len(records["dispatches"]) + len(records["receipts"]) == 64
    assert len(skills_state(c)["loaded"]) == 1
    overflow = next_candidate(c)
    before = snapshot(c)
    with pytest.raises(ValueError) as error:
        begin(c, overflow, "beyond-cap")
    assert getattr(error.value, "code", None) == "bounds_exceeded" and snapshot(c) == before
