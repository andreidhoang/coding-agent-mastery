"""2026-10-09 authority audit: targeted expected-behavior regressions."""

import pytest

from service.artifacts import LocalArtifacts, digest_json
from service.execution import Workspace, tree_digest
from service.harness import ToolBroker
from service.integration import candidate_manifest
from service.protocol import ToolCall
from service.recovery import restore_checkpoint
from service.storage import RuntimeStore


BASE = {"a.py": "old\n"}


@pytest.fixture
def authority(tmp_path):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "authority.db"), artifacts)
    yield store, artifacts
    store.close()


def setup_task(store, tenant="tenant", nodes=("a",)):
    task = store.submit(
        tenant,
        "submit",
        {
            "repo_id": "fixture",
            "base_revision": tree_digest(BASE),
            "requirements": ["change a"],
            "budget_units": 100,
        },
    )
    store.set_graph(tenant, task["task_id"], 1, [{"node_id": n, "allowed_paths": ["a.py"]} for n in nodes])
    return task


def owner_for(store, task, node="a"):
    return store.claim(task["tenant_id"], task["task_id"], node, "claim-" + node, 20, 60)["owner"]


def test_billing_only_receipt_preserves_known_effect_artifact(authority):
    store, artifacts = authority
    task = setup_task(store)
    owner = owner_for(store, task)
    store.begin_dispatch(owner, "action", "dispatch", "read", digest_json({}), 5)
    ref = artifacts.put_json("tenant", task["task_id"], {"result": "immutable"})
    store.finish_dispatch("tenant", "dispatch", "effect-receipt", "succeeded", None, ref)
    settled = store.finish_dispatch("tenant", "dispatch", "billing-receipt", "succeeded", 2)
    assert settled["result_ref"] == ref


def test_terminal_tool_dispatch_without_artifact_never_executes_again(authority, tmp_path):
    store, artifacts = authority
    task = setup_task(store)
    owner = owner_for(store, task)
    call = ToolCall("call", "run_tests", {})
    key = digest_json({"attempt": owner["attempt_id"], "call": call.call_id})[:32]
    dispatch_id = "dispatch-" + key
    store.begin_dispatch(owner, "action-" + key, dispatch_id, call.name, call.digest, 0)
    store.finish_dispatch("tenant", dispatch_id, "prior-receipt", "succeeded", 0)
    calls = []
    broker = ToolBroker(
        store,
        artifacts,
        owner,
        Workspace(tmp_path / "workspace", ["a.py"]),
        ["run_tests"],
        verifier=lambda files: calls.append(files),
    )
    try:
        broker.execute(call)
    except Exception:
        pass  # Rejecting a missing receipt is safe only before a physical effect.
    assert calls == []


def test_candidate_commit_ack_loss_retry_returns_same_receipt(authority):
    store, _ = authority
    task = setup_task(store)
    owner = owner_for(store, task)
    manifest = candidate_manifest(BASE, {"a.py": "new\n"}, ["a.py"], owner, ["change a"])
    accepted = store.accept_candidate(owner, manifest)
    retried = store.accept_candidate(owner, manifest)
    assert retried == accepted
    assert len(store.snapshot("tenant", task["task_id"])["candidates"]) == 1


def test_checkpoint_restores_when_only_sibling_was_in_flight(authority):
    store, artifacts = authority
    task = setup_task(store, nodes=("a", "b"))
    owner_a, owner_b = owner_for(store, task, "a"), owner_for(store, task, "b")
    store.begin_dispatch(owner_b, "sibling-action", "sibling-dispatch", "read", digest_json({}), 1)
    workspace = artifacts.put_json("tenant", task["task_id"], BASE)
    payload = artifacts.put_json(
        "tenant",
        task["task_id"],
        {
            "messages": [],
            "evidence": [],
            "workspace_ref": workspace,
        },
    )
    checkpoint = store.checkpoint(owner_a, {"artifact_ref": payload, "next_turn": 0})
    store.finish_dispatch("tenant", "sibling-dispatch", "sibling-receipt", "succeeded", 1)
    restored = restore_checkpoint(store, artifacts, "tenant", task["task_id"], checkpoint["checkpoint_id"])
    assert restored["files"] == BASE


def test_valid_tenant_dispatch_identifiers_cannot_alias(authority):
    store, _ = authority
    task_one, task_two = setup_task(store, "a:b"), setup_task(store, "a")
    owner_one, owner_two = owner_for(store, task_one), owner_for(store, task_two)
    first = store.begin_dispatch(owner_one, "action", "c", "read", digest_json({}), 1)
    second = store.begin_dispatch(owner_two, "action", "b:c", "read", digest_json({}), 1)
    assert first["tenant_id"] != second["tenant_id"]


def test_billing_rejects_rebinding_effect_artifact(authority):
    from service.contracts import Conflict

    store, artifacts = authority
    task = setup_task(store)
    owner = owner_for(store, task)
    store.begin_dispatch(owner, "action", "dispatch", "read", digest_json({}), 5)
    first = artifacts.put_json("tenant", task["task_id"], {"result": "first"})
    changed = artifacts.put_json("tenant", task["task_id"], {"result": "changed"})
    store.finish_dispatch("tenant", "dispatch", "effect", "succeeded", None, first)
    frontier = store.get_task("tenant", task["task_id"])["event_sequence"]
    with pytest.raises(Conflict, match="evidence"):
        store.finish_dispatch("tenant", "dispatch", "billing", "succeeded", 2, changed)
    assert store.get_task("tenant", task["task_id"])["event_sequence"] == frontier
    assert store.snapshot("tenant", task["task_id"])["dispatches"][0]["result_ref"] == first


def test_candidate_retry_after_revocation_is_receipt_only_changed_body_conflicts(authority):
    from service.contracts import Conflict, Fenced

    store, _ = authority
    task = setup_task(store)
    owner = owner_for(store, task)
    manifest = candidate_manifest(BASE, {"a.py": "new\n"}, ["a.py"], owner, ["change a"])
    accepted = store.accept_candidate(owner, manifest)
    store.cancel("tenant", task["task_id"], "cancel")
    before = store.snapshot("tenant", task["task_id"])
    assert store.accept_candidate(owner, manifest) == accepted
    assert store.snapshot("tenant", task["task_id"]) == before
    with pytest.raises(Conflict, match="manifest"):
        store.accept_candidate(owner, {**manifest, "tree_digest": "a" * 64})
    with pytest.raises(Fenced):
        store.begin_dispatch(owner, "new-action", "new-dispatch", "read", digest_json({}), 0)


def test_concurrent_exact_candidate_retries_commit_once(authority):
    from concurrent.futures import ThreadPoolExecutor

    store, _ = authority
    task = setup_task(store)
    owner = owner_for(store, task)
    manifest = candidate_manifest(BASE, {"a.py": "new\n"}, ["a.py"], owner, ["change a"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.accept_candidate(owner, manifest), range(2)))
    assert results[0] == results[1]
    events = store.events("tenant", task["task_id"])["events"]
    assert sum(event["kind"] == "candidate.accepted" for event in events) == 1


def test_checkpoint_own_unknown_still_vetoes_restore(authority):
    store, artifacts = authority
    task = setup_task(store)
    owner = owner_for(store, task)
    store.begin_dispatch(owner, "own-action", "own-dispatch", "read", digest_json({}), 1)
    workspace = artifacts.put_json("tenant", task["task_id"], BASE)
    payload = artifacts.put_json(
        "tenant", task["task_id"], {"messages": [], "evidence": [], "workspace_ref": workspace}
    )
    checkpoint = store.checkpoint(owner, {"artifact_ref": payload, "next_turn": 0})
    assert checkpoint["dispatch_frontier"] == ["own-dispatch"]
    assert checkpoint["pending_dispatches"][0]["attempt_id"] == owner["attempt_id"]
    with pytest.raises(ValueError, match="reconciliation"):
        restore_checkpoint(store, artifacts, "tenant", task["task_id"], checkpoint["checkpoint_id"])


def test_valid_tenant_candidate_identifiers_cannot_alias(authority):
    store, _ = authority
    task_one, task_two = setup_task(store, "a:b"), setup_task(store, "a")
    owner_one, owner_two = owner_for(store, task_one), owner_for(store, task_two)
    manifests = [
        candidate_manifest(BASE, {"a.py": "new\n"}, ["a.py"], owner, ["change a"])
        for owner in (owner_one, owner_two)
    ]
    first = store.accept_candidate(owner_one, {**manifests[0], "candidate_id": "c"})
    second = store.accept_candidate(owner_two, {**manifests[1], "candidate_id": "b:c"})
    assert first["tenant_id"] != second["tenant_id"]


@pytest.mark.parametrize("body", ["1e999", "-1e999", '{"nested":[{"value":1e999}]}'])
def test_contract_json_rejects_exponent_overflow_recursively(body):
    from service.contracts import parse_json

    with pytest.raises(ValueError, match="nonfinite"):
        parse_json(body)


def downgrade_disposable_fixture_to_v1(store):
    """Test-only construction of historical-format rows. Never touches prior runs."""
    import sqlalchemy as sa
    from service.storage import TABLES, metadata, schema_versions

    with store.engine.begin() as c:
        if c.dialect.name == "postgresql":
            c.exec_driver_sql("SET LOCAL cam.writer_schema = '2'")
            for table in metadata.sorted_tables:
                c.exec_driver_sql(f'DROP TRIGGER IF EXISTS "cam_v2_{table.name}" ON "{table.name}"')
        else:
            names = (
                c.execute(
                    sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'cam_v2_%'")
                )
                .scalars()
                .all()
            )
            for name in names:
                c.exec_driver_sql(f'DROP TRIGGER "{name}"')
        for name, field in (("dispatches", "dispatch_id"), ("candidates", "candidate_id")):
            table = TABLES[name]
            rows = [dict(row) for row in c.execute(sa.select(table)).mappings()]
            c.execute(table.delete())
            if rows:
                c.execute(
                    table.insert(),
                    [{**row, "id": row["tenant_id"] + ":" + row["data"][field]} for row in rows],
                )
        c.execute(schema_versions.delete())
        c.execute(schema_versions.insert().values(version=1))


def seed_legacy_evidence(store):
    """A settled read followed by accepted candidate has both rekeyed entity types."""
    task = setup_task(store)
    owner = owner_for(store, task)
    store.begin_dispatch(owner, "action", "dispatch", "read", digest_json({}), 5)
    store.finish_dispatch("tenant", "dispatch", "receipt", "succeeded", 2)
    manifest = candidate_manifest(BASE, {"a.py": "new\n"}, ["a.py"], owner, ["change a"])
    candidate = store.accept_candidate(owner, manifest)
    return task, candidate, store.snapshot("tenant", task["task_id"])


def test_explicit_sqlite_migration_preserves_original_copy_and_blocks_legacy_writes(tmp_path):
    import hashlib
    import shutil
    import sqlalchemy as sa
    from service.contracts import Unsupported
    from service.migrations.v2_identity import migrate_v1_to_v2, record_key
    from service.storage import TABLES, schema_versions

    original = tmp_path / "historical-fixture.sqlite"
    source = RuntimeStore("sqlite:///" + str(original))
    task, candidate, snapshot = seed_legacy_evidence(source)
    downgrade_disposable_fixture_to_v1(source)
    source.close()
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    copied = tmp_path / "migration-copy.sqlite"
    shutil.copyfile(original, copied)
    url = "sqlite:///" + str(copied)
    with pytest.raises(Unsupported, match="migration"):
        RuntimeStore(url)
    # This opened legacy engine/connection has no v2 UDF even after migration.
    legacy_engine = sa.create_engine(url)
    with legacy_engine.connect() as legacy:
        assert legacy.execute(sa.select(schema_versions.c.version)).scalar_one() == 1
        legacy.rollback()
        report = migrate_v1_to_v2(url)
        assert report["converted"] == {"dispatches": 1, "candidates": 1}
        with pytest.raises(sa.exc.DBAPIError):
            legacy.execute(TABLES["tasks"].update().values(data={"poison": True}))
        legacy.rollback()
        with pytest.raises(sa.exc.DBAPIError):
            legacy.execute(schema_versions.insert().values(version=1))
        legacy.rollback()
        assert legacy.execute(sa.select(schema_versions.c.version)).scalars().all() == [2]
    legacy_engine.dispose()
    migrated = RuntimeStore(url)
    assert migrated.snapshot("tenant", task["task_id"]) == snapshot
    with migrated.engine.connect() as c:
        assert c.execute(sa.select(TABLES["dispatches"].c.id)).scalar_one() == record_key(
            "tenant", "dispatch"
        )
        assert c.execute(sa.select(TABLES["candidates"].c.id)).scalar_one() == record_key(
            "tenant", candidate["candidate_id"]
        )
    migrated.cancel("tenant", task["task_id"], "new-v2-writer")
    migrated.close()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before


def test_sqlite_failed_migration_rolls_back_keys_version_and_triggers(tmp_path, monkeypatch):
    import sqlalchemy as sa
    from service.migrations import v2_identity
    from service.storage import TABLES, schema_versions

    path = tmp_path / "legacy-disposable.sqlite"
    source = RuntimeStore("sqlite:///" + str(path))
    seed_legacy_evidence(source)
    downgrade_disposable_fixture_to_v1(source)
    source.close()
    engine = sa.create_engine("sqlite:///" + str(path))
    with engine.connect() as c:
        before = c.execute(sa.select(TABLES["dispatches"])).mappings().all()
    real_install = v2_identity.install_writer_fences

    def interrupted(c, tables):
        real_install(c, tables)
        raise RuntimeError("injected migration crash after trigger installation")

    monkeypatch.setattr(v2_identity, "install_writer_fences", interrupted)
    with pytest.raises(RuntimeError, match="injected"):
        v2_identity.migrate_v1_to_v2(str(engine.url))
    with engine.connect() as c:
        assert c.execute(sa.select(schema_versions.c.version)).scalars().all() == [1]
        assert c.execute(sa.select(TABLES["dispatches"])).mappings().all() == before
        assert (
            c.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'cam_v2_%'")
            ).all()
            == []
        )
        c.execute(schema_versions.insert().values(version=999))  # No partially committed writer fence.
        c.rollback()
    engine.dispose()


@pytest.mark.parametrize("version_state", ["empty", "missing"])
def test_populated_unversioned_legacy_database_is_rejected_without_mutation(tmp_path, version_state):
    import hashlib
    from service.contracts import Unsupported
    from service.storage import schema_versions

    path = tmp_path / "unversioned-legacy.sqlite"
    url = "sqlite:///" + str(path)
    source = RuntimeStore(url)
    seed_legacy_evidence(source)
    downgrade_disposable_fixture_to_v1(source)
    with source.engine.begin() as c:
        if version_state == "empty":
            c.execute(schema_versions.delete())
        else:
            schema_versions.drop(c)
    source.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(Unsupported):
        reopened = RuntimeStore(url)
        reopened.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_unversioned_rows_that_appear_after_preflight_are_rejected_before_bootstrap_writes(
    tmp_path, monkeypatch
):
    import hashlib
    import sqlalchemy as sa
    from service.contracts import Unsupported
    from service.storage import authority, metadata

    path = tmp_path / "bootstrap-race.sqlite"
    url = "sqlite:///" + str(path)
    engine = sa.create_engine(url)
    metadata.create_all(engine)  # Entirely empty precreated metadata is valid.
    original = RuntimeStore._bootstrap_versions
    checks = 0
    after_legacy_write = None

    def concurrent_write(c):
        nonlocal checks, after_legacy_write
        checks += 1
        result = original(c)
        if checks == 1:
            with engine.begin() as old:
                old.execute(authority.insert().values(id=1, data={"legacy": "must not reinterpret"}))
            after_legacy_write = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    monkeypatch.setattr(RuntimeStore, "_bootstrap_versions", staticmethod(concurrent_write))
    with pytest.raises(Unsupported, match="unversioned"):
        RuntimeStore(url)
    assert checks == 2  # A separate serialized check found the race.
    assert hashlib.sha256(path.read_bytes()).hexdigest() == after_legacy_write
    engine.dispose()


def test_entirely_empty_precreated_metadata_initializes_validly(tmp_path):
    import sqlalchemy as sa
    from service.storage import metadata

    url = "sqlite:///" + str(tmp_path / "precreated-empty.sqlite")
    engine = sa.create_engine(url)
    metadata.create_all(engine)
    engine.dispose()
    store = RuntimeStore(url)
    task = setup_task(store)
    assert store.get_task("tenant", task["task_id"])["task_id"] == task["task_id"]
    store.close()


def test_migration_cli_accepts_url_environment_name_without_url_in_argv(tmp_path, monkeypatch, capsys):
    import sys
    from service.migrations import v2_identity

    url = "sqlite:///" + str(tmp_path / "cli-copy.sqlite")
    source = RuntimeStore(url)
    seed_legacy_evidence(source)
    downgrade_disposable_fixture_to_v1(source)
    source.close()
    monkeypatch.setenv("CAM_DISPOSABLE_MIGRATION_URL", url)
    monkeypatch.setattr(sys, "argv", ["migration", "--url-env", "CAM_DISPOSABLE_MIGRATION_URL"])
    v2_identity.main()
    assert '"to_version": 2' in capsys.readouterr().out
