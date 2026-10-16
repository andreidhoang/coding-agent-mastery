"""Opt-in real PostgreSQL dialect/row-lock evidence; no simulated backend."""

import concurrent.futures
import os
import time
import uuid

import pytest
import sqlalchemy as sa
from service.storage import RuntimeStore
from service.contracts import BudgetExceeded, CapacityExceeded, Fenced, ResetRequired
from service.execution import tree_digest

pytestmark = pytest.mark.skipif(
    not os.environ.get("CAM_TEST_POSTGRES_URL"), reason="CAM_TEST_POSTGRES_URL not configured"
)


@pytest.fixture
def postgres_store():
    url = os.environ["CAM_TEST_POSTGRES_URL"]
    namespace = "test_" + uuid.uuid4().hex
    admin = sa.create_engine(url)
    with admin.begin() as c:
        c.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    parsed = sa.engine.make_url(url).update_query_dict({"options": "-csearch_path=" + namespace})
    store = RuntimeStore(
        parsed.render_as_string(hide_password=False),
        service_slot_limit=2,
        tenant_slot_limit=2,
        service_budget_units=100,
        tenant_budget_units=100,
    )
    try:
        yield store
    finally:
        store.close()
        with admin.begin() as c:
            c.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


def make_task(store, key, budget=100, deadline=None):
    task = store.submit(
        "tenant",
        key,
        {
            "repo_id": "fixture",
            "base_revision": tree_digest({"a.py": "bad"}),
            "requirements": ["fix"],
            "budget_units": budget,
            "execution_deadline": deadline or time.time() + 60,
            "review_deadline": time.time() + 120,
        },
    )
    store.set_graph("tenant", task["task_id"], 1, [{"node_id": "a"}, {"node_id": "b"}])
    return task


def test_postgres_row_lock_serializes_shared_budget_and_one_node(postgres_store):
    store = postgres_store
    task = make_task(store, "first")

    def claim(node):
        try:
            return store.claim("tenant", task["task_id"], node, "claim-" + node, 60, 30)
        except (BudgetExceeded, CapacityExceeded) as exc:
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(claim, ["a", "b"]))
    assert sum(isinstance(x, dict) for x in result) == 1
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 60
    granted = next(x for x in result if isinstance(x, dict))
    with pytest.raises(CapacityExceeded):
        store.claim("tenant", task["task_id"], granted["node_id"], "competing", 1, 30)


def test_postgres_uncertain_cancel_late_receipt_restore(postgres_store):
    store = postgres_store
    task = make_task(store, "fault")
    grant = store.claim("tenant", task["task_id"], "a", "claim", 40, 30)
    store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 12)
    store.finish_dispatch("tenant", "dispatch", "lost", "unknown")
    cursor = store.events("tenant", task["task_id"])["cursor"]
    store.cancel("tenant", task["task_id"], "cancel")
    store.retire_sandbox("tenant", grant["sandbox_id"], {"supervisor": "trusted", "exit_observed": True})
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 12
    store.finish_dispatch("tenant", "dispatch", "bill", "succeeded", 9)
    store.finish_dispatch("tenant", "dispatch", "bill", "succeeded", 9)
    assert store.get_task("tenant", task["task_id"])["budget"]["spent"] == 9
    store.quarantine_restore("new-incarnation", {"backup": "trusted"})
    with pytest.raises(ResetRequired):
        store.events("tenant", task["task_id"], cursor)
    with pytest.raises(Fenced):
        store.heartbeat(grant["owner"], 30)


def test_postgres_database_time_final_cutoff(postgres_store, monkeypatch):
    store = postgres_store
    with store.engine.connect() as connection:
        database_time = float(connection.exec_driver_sql(
            "SELECT EXTRACT(EPOCH FROM clock_timestamp())").scalar_one())
    deadline = database_time + 3.0
    task = make_task(store, "deadline", deadline=deadline)
    grant = store.claim("tenant", task["task_id"], "a", "claim", 10, 30)
    with store.engine.connect() as connection:
        connection.execute(sa.text(
            "SELECT pg_sleep(LEAST(3.0, GREATEST(0.0, "
            ":deadline + 0.02 - EXTRACT(EPOCH FROM clock_timestamp()))))"), {"deadline": deadline})
        assert float(connection.exec_driver_sql(
            "SELECT EXTRACT(EPOCH FROM clock_timestamp())").scalar_one()) > deadline
    # A lagging host clock must not waive the authoritative database cutoff.
    with monkeypatch.context() as host_clock:
        host_clock.setattr(time, "time", lambda: deadline - 10)
        with pytest.raises(Fenced, match="database execution deadline elapsed"):
            store.heartbeat(grant["owner"], 30)
        with pytest.raises(Fenced, match="database execution deadline elapsed"):
            store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 1)


def test_postgres_explicit_migration_rekeys_and_blocks_already_open_legacy_writer(postgres_store):
    from test_audit_authority import downgrade_disposable_fixture_to_v1, seed_legacy_evidence
    from service.contracts import Unsupported
    from service.migrations.v2_identity import migrate_v1_to_v2, record_key
    from service.storage import TABLES, schema_versions

    source = postgres_store
    task, candidate, snapshot = seed_legacy_evidence(source)
    downgrade_disposable_fixture_to_v1(source)
    url = source.engine.url.render_as_string(hide_password=False)
    with pytest.raises(Unsupported, match="migration"):
        RuntimeStore(url)
    legacy_engine = sa.create_engine(url)
    with legacy_engine.connect() as legacy:
        assert legacy.execute(sa.select(schema_versions.c.version)).scalar_one() == 1
        legacy.rollback()
        report = migrate_v1_to_v2(url)
        assert report["converted"] == {"dispatches": 1, "candidates": 1}
        with pytest.raises(sa.exc.DBAPIError, match="writer protocol"):
            legacy.execute(TABLES["tasks"].update().values(data={"poison": True}))
        legacy.rollback()
        with pytest.raises(sa.exc.DBAPIError, match="writer protocol"):
            legacy.execute(schema_versions.insert().values(version=1))
        legacy.rollback()
        assert legacy.execute(sa.select(schema_versions.c.version)).scalars().all() == [2]
    legacy_engine.dispose()
    fresh = RuntimeStore(url)
    assert fresh.snapshot("tenant", task["task_id"]) == snapshot
    with fresh.engine.connect() as c:
        assert c.execute(sa.select(TABLES["dispatches"].c.id)).scalar_one() == record_key(
            "tenant", "dispatch"
        )
        assert c.execute(sa.select(TABLES["candidates"].c.id)).scalar_one() == record_key(
            "tenant", candidate["candidate_id"]
        )
    fresh.cancel("tenant", task["task_id"], "v2-writer")
    fresh.close()


def test_postgres_migration_failure_rolls_back_data_version_and_triggers(postgres_store, monkeypatch):
    from test_audit_authority import downgrade_disposable_fixture_to_v1, seed_legacy_evidence
    from service.migrations import v2_identity
    from service.storage import TABLES, schema_versions

    source = postgres_store
    seed_legacy_evidence(source)
    downgrade_disposable_fixture_to_v1(source)
    url = source.engine.url.render_as_string(hide_password=False)
    engine = sa.create_engine(url)
    with engine.connect() as c:
        before = c.execute(sa.select(TABLES["dispatches"])).mappings().all()
    real_install = v2_identity.install_writer_fences

    def interrupted(c, tables):
        real_install(c, tables)
        raise RuntimeError("injected migration crash after PostgreSQL trigger installation")

    monkeypatch.setattr(v2_identity, "install_writer_fences", interrupted)
    with pytest.raises(RuntimeError, match="injected"):
        v2_identity.migrate_v1_to_v2(url)
    with engine.connect() as c:
        assert c.execute(sa.select(schema_versions.c.version)).scalars().all() == [1]
        assert c.execute(sa.select(TABLES["dispatches"])).mappings().all() == before
        trigger_count = c.execute(
            sa.text(
                "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=current_schema() AND trigger_name LIKE 'cam_v2_%'"
            )
        ).scalar_one()
        assert trigger_count == 0
        c.execute(schema_versions.insert().values(version=999))  # Failed DDL left no writer guard.
        c.rollback()
    engine.dispose()


def test_postgres_concurrent_initializers_on_precreated_empty_schema(postgres_store):
    from service.storage import metadata, schema_versions

    # This UUID namespace belongs solely to this test; metadata already exists.
    source = postgres_store
    with source.engine.begin() as c:
        c.exec_driver_sql("SET LOCAL cam.writer_schema = '2'")
        for table in metadata.sorted_tables:
            c.exec_driver_sql(f'DROP TRIGGER IF EXISTS "cam_v2_{table.name}" ON "{table.name}"')
        for table in reversed(metadata.sorted_tables):
            c.execute(table.delete())
    url = source.engine.url.render_as_string(hide_password=False)

    def initialize(_):
        return RuntimeStore(url)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        stores = list(pool.map(initialize, range(2)))
    try:
        assert stores[0].execution_incarnation == stores[1].execution_incarnation
        with stores[0].engine.connect() as c:
            assert c.execute(sa.select(schema_versions.c.version)).scalars().all() == [2]
        task = make_task(stores[0], "after-concurrent-init")
        assert stores[1].get_task("tenant", task["task_id"])["task_id"] == task["task_id"]
    finally:
        for store in stores:
            store.close()


@pytest.mark.parametrize("version_state", ["empty", "missing"])
def test_postgres_populated_unversioned_legacy_rejected_without_row_or_ddl_changes(
    postgres_store, version_state
):
    from test_audit_authority import downgrade_disposable_fixture_to_v1, seed_legacy_evidence
    from service.contracts import Unsupported
    from service.storage import metadata, schema_versions

    source = postgres_store
    seed_legacy_evidence(source)
    downgrade_disposable_fixture_to_v1(source)
    with source.engine.begin() as c:
        if version_state == "empty":
            c.execute(schema_versions.delete())
        else:
            schema_versions.drop(c)
    url = source.engine.url.render_as_string(hide_password=False)

    def contents():
        with source.engine.connect() as c:
            inspector = sa.inspect(c)
            tables = inspector.get_table_names()
            rows = {
                table.name: [dict(row) for row in c.execute(sa.select(table)).mappings()]
                for table in metadata.sorted_tables
                if table.name in tables
            }
            ddl = c.execute(
                sa.text(
                    "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname=current_schema() ORDER BY tablename,indexname"
                )
            ).all()
            triggers = c.execute(
                sa.text(
                    "SELECT event_object_table,trigger_name,action_statement FROM information_schema.triggers WHERE trigger_schema=current_schema() ORDER BY event_object_table,trigger_name"
                )
            ).all()
            return tables, rows, ddl, triggers

    before = contents()
    with pytest.raises(Unsupported, match="unversioned"):
        RuntimeStore(url)
    assert contents() == before
