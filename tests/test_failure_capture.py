"""Pinned, bounded read evidence against real SQLite and optional PostgreSQL."""

import concurrent.futures
import threading

import pytest
import sqlalchemy as sa

from failure_adapter_helpers import (
    capture,
    failure_store,
    failure_postgres_store,
    fingerprint,
    make_task,
    unknown_dispatch,
)
from service.artifacts import canonical_bytes
from service.contracts import NotFound
from service.storage import TABLES, event_rows

# Pytest registers imported fixtures; these names are intentionally imported.
assert failure_store and failure_postgres_store


def test_capture_deterministic_detached_complete_and_read_only(failure_store):
    store = failure_store
    task, _ = unknown_dispatch(store)
    before = fingerprint(store)
    first = capture(store, task)
    second = capture(store, task)
    assert first == second
    assert first["capture"]["status"] == "complete"
    assert first["capture"]["source_bytes"] == len(
        canonical_bytes({key: first[key] for key in ("snapshot", "receipts", "submissions", "events")})
    )
    assert [e["sequence"] for e in first["events"]] == list(range(1, first["capture"]["frontier"] + 1))
    assert "cursor_secret" not in canonical_bytes(first).decode()
    first["snapshot"]["task"]["contract"]["requirements"].append("outside mutation")
    assert capture(store, task) == second
    assert fingerprint(store) == before


@pytest.mark.parametrize(
    "option,value",
    [
        ("max_rows", True),
        ("max_rows", 0),
        ("max_rows", 10001),
        ("max_events", 0),
        ("max_events", 10001),
        ("max_source_bytes", 1023),
        ("max_source_bytes", 16777217),
        ("page_size", 0),
        ("page_size", 1001),
        ("page_size", 1.5),
    ],
)
def test_capture_limit_schema_is_strict(failure_store, option, value):
    task = make_task(failure_store)
    with pytest.raises(ValueError):
        failure_store.capture_failure_source("tenant", task["task_id"], **{option: value})


@pytest.mark.parametrize("option,value", [("max_rows", 1), ("max_events", 1), ("max_source_bytes", 1024)])
def test_preflight_rejects_before_snapshot_collection_decode(failure_store, monkeypatch, option, value):
    task, _ = unknown_dispatch(failure_store)

    def collection_decode_forbidden(*args, **kwargs):
        raise AssertionError("preflight must reject before collection decoding")

    monkeypatch.setattr(failure_store, "_snapshot", collection_decode_forbidden)
    monkeypatch.setattr(failure_store, "_list", collection_decode_forbidden)
    with pytest.raises(ValueError, match="^capture_limit_exceeded:"):
        failure_store.capture_failure_source("tenant", task["task_id"], **{option: value})


def test_large_row_preflight_before_collection_decode(failure_store, monkeypatch):
    task = make_task(failure_store)
    with failure_store._tx() as (c, _):
        table = TABLES["nodes"]
        row = c.execute(sa.select(table.c.data)).scalar_one()
        row["large_test_data"] = "x" * 100_000
        c.execute(table.update().values(data=row))
    monkeypatch.setattr(failure_store, "_snapshot", lambda *a: pytest.fail("decoded oversized row"))
    with pytest.raises(ValueError, match="^capture_limit_exceeded:"):
        failure_store.capture_failure_source("tenant", task["task_id"], max_source_bytes=4096)


def test_missing_task_and_other_tenant_not_silently_empty(failure_store):
    task = make_task(failure_store)
    for tenant, task_id in (("other", task["task_id"]), ("tenant", "missing")):
        with pytest.raises(NotFound):
            failure_store.capture_failure_source(tenant, task_id)


def pinned_read_with_concurrent_writer(store):
    task, dispatch = unknown_dispatch(store)
    before = capture(store, task)
    pinned, committed = threading.Event(), threading.Event()
    reader_thread = [None]
    hit = [False]

    def barrier(connection, cursor, statement, parameters, context, executemany):
        if threading.get_ident() == reader_thread[0] and not hit[0] and "FROM tasks" in statement:
            hit[0] = True
            pinned.set()
            assert committed.wait(10), "concurrent writer did not commit while read transaction was pinned"

    sa.event.listen(store.engine, "after_cursor_execute", barrier)

    def read():
        reader_thread[0] = threading.get_ident()
        return store.capture_failure_source("tenant", task["task_id"], page_size=1)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(read)
            assert pinned.wait(10), "capture never read task on pinned transaction"
            store.finish_dispatch("tenant", dispatch, "late-billing", "unknown", 9)
            committed.set()
            observed = result.result(timeout=10)
    finally:
        committed.set()
        sa.event.remove(store.engine, "after_cursor_execute", barrier)
    # Limits differ because the read intentionally pages one event at a time.
    before["capture"]["limits"]["page_size"] = 1
    assert observed == before
    after = capture(store, task)
    assert after["capture"]["frontier"] == before["capture"]["frontier"] + 1
    assert after["snapshot"]["budget"]["spent"] == 9
    assert observed["snapshot"]["budget"]["spent"] == 0


def test_sqlite_wal_barrier_real_committed_writer(failure_store):
    pinned_read_with_concurrent_writer(failure_store)


@pytest.mark.postgres
def test_postgres_repeatable_read_barrier_real_committed_writer(failure_postgres_store):
    pinned_read_with_concurrent_writer(failure_postgres_store)


@pytest.mark.parametrize("defect", ["middle", "prefix", "incarnation"])
def test_capture_history_damage_is_incomplete(failure_store, defect):
    task, _ = unknown_dispatch(failure_store)
    with failure_store._tx() as (c, _):
        if defect == "incarnation":
            row = c.execute(sa.select(event_rows).order_by(event_rows.c.sequence)).mappings().first()
            data = dict(row["data"])
            data["service_incarnation"] = "old-incarnation"
            c.execute(event_rows.update().where(event_rows.c.event_id == row["event_id"]).values(data=data))
        else:
            sequence = 1 if defect == "prefix" else 3
            c.execute(event_rows.delete().where(event_rows.c.sequence == sequence))
    observed = capture(failure_store, task)
    assert observed["capture"]["status"] == "incomplete"
    assert ("mixed_incarnation" if defect == "incarnation" else "event_sequence_gap") in observed["capture"][
        "reasons"
    ]


def test_capture_propagates_database_failure(failure_store, monkeypatch):
    task = make_task(failure_store)
    from contextlib import contextmanager

    @contextmanager
    def failed_read():
        raise RuntimeError("injected database transport error")
        yield

    monkeypatch.setattr(failure_store, "_read", failed_read)
    with pytest.raises(RuntimeError, match="transport"):
        capture(failure_store, task)


def test_huge_frontier_is_bounded_gap_not_range_allocation(failure_store):
    task = make_task(failure_store)
    with failure_store._tx() as (c, _):
        table = TABLES["tasks"]
        row = c.execute(sa.select(table.c.data)).scalar_one()
        row["event_sequence"] = 10**12
        c.execute(table.update().values(data=row))
    data = capture(failure_store, task)
    assert data["capture"]["status"] == "incomplete"
    assert "event_sequence_gap" in data["capture"]["reasons"]


def test_filename_identity_words_are_data_not_scope(failure_store):
    from service.integration import candidate_manifest

    base = {"task_id": "original plain text", "tenant_id": "another original"}
    task = make_task(failure_store, base=base)
    grant = failure_store.claim("tenant", task["task_id"], "patch", "claim", 40, 60)
    manifest = candidate_manifest(
        base,
        {"task_id": "changed plain text", "tenant_id": "another original"},
        list(base),
        grant["owner"],
        task["contract"]["requirements"],
    )
    failure_store.accept_candidate(grant["owner"], manifest)
    data = capture(failure_store, task)
    assert data["capture"]["status"] == "complete"
