"""Independent controls for the frozen offline-serving contract.

Only owned local processes, temporary roots and UUID PostgreSQL schemas are used.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from service.api import create_app
from service.artifacts import canonical_bytes, digest_bytes
from service.contracts import CapacityExceeded, Conflict, Unsupported
from service.offline_server import OfflineService, SENTINEL, SENTINEL_SCOPE
from service.serving_config import fixture_contract, load_tokens
from service.storage import RuntimeStore, TABLES, authority, event_rows
from workloads import list_tasks


TOKEN = "independent-synthetic-serving-credential"


def config(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    item = fixture_contract(list_tasks(tier="T1")[0].task_id, time.time() + 600, time.time() + 1200)
    return {
        "schema": 1, "mode": "offline_fixture_v1", "root": str((tmp_path / "root").resolve()),
        "host": "127.0.0.1", "port": port,
        "limits": {"service_slot_limit": 3, "tenant_slot_limit": 3,
                   "service_budget_units": 100000, "tenant_budget_units": 100000},
        "admission_policy": {"schema": 1, "service_pending_limit": 3, "tenant_pending_limit": 1},
        "worker": {"poll_ms": 100, "shutdown_seconds": 2},
        "principals": [{"tenant_id": "review", "subject_id": "independent", "repositories": [item["repo_id"]],
                        "can_review": False, "profiles": ["production"], "token_env": "CAM_SERVE_TOKEN_REVIEW"}],
        "catalog": [item],
    }


def service_for(cfg):
    return OfflineService(cfg, load_tokens(cfg, {"CAM_SERVE_TOKEN_REVIEW": TOKEN}))


def simple_contract():
    return {"repo_id": "independent", "base_revision": "frozen", "requirements": ["exercise cap"]}


def eventually(predicate, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError("bounded observation did not arrive")


@contextmanager
def configured_service(cfg):
    instance = service_for(cfg)
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()


@pytest.fixture(params=["sqlite", "postgres"])
def admission_url(request, tmp_path):
    if request.param == "sqlite":
        yield "sqlite:///" + str(tmp_path / "independent.sqlite")
        return
    base = os.environ.get("CAM_TEST_POSTGRES_URL")
    if not base:
        pytest.skip("explicit local PostgreSQL URL absent")
    namespace = "serving_independent_" + uuid.uuid4().hex
    admin = sa.create_engine(base)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    parsed = sa.engine.make_url(base).update_query_dict({"options": "-csearch_path=" + namespace})
    try:
        yield parsed.render_as_string(hide_password=False)
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


def counts(store):
    with store._read() as connection:
        return {name: connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
                for name, table in {"tasks": TABLES["tasks"], "submissions": TABLES["submissions"],
                                    "outbox": TABLES["outbox"], "events": event_rows}.items()}


def test_independent_atomic_multitenant_race_and_retry(admission_url):
    policy = {"schema": 1, "service_pending_limit": 3, "tenant_pending_limit": 1}
    first = RuntimeStore(admission_url, admission_policy=policy)
    # Deliberately omit the constructor policy on the other writers.
    stores = [first] + [RuntimeStore(admission_url) for _ in range(7)]
    barrier = threading.Barrier(8)

    def submit(index):
        barrier.wait(timeout=10)
        try:
            return stores[index].submit("tenant-" + str(index), "key", simple_contract())
        except CapacityExceeded:
            return None

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(submit, range(8)))
        winners = [value for value in results if value]
        assert len(winners) == 3
        assert counts(first) == {"tasks": 3, "submissions": 3, "outbox": 3, "events": 3}
        first.set_admission(False)
        before = counts(first)
        for winner in winners:
            assert stores[-1].submit(winner["tenant_id"], "key", simple_contract())["task_id"] == winner["task_id"]
            with pytest.raises(Conflict):
                stores[-1].submit(winner["tenant_id"], "key", dict(simple_contract(), base_revision="changed"))
        assert counts(first) == before
    finally:
        for store in stores:
            store.close()


def test_independent_explicit_policy_drift_cannot_reopen(admission_url):
    policy = {"schema": 1, "service_pending_limit": 3, "tenant_pending_limit": 1}
    store = RuntimeStore(admission_url, admission_policy=policy)
    store.submit("tenant", "first", simple_contract())
    before = counts(store)
    try:
        with pytest.raises(Unsupported):
            RuntimeStore(admission_url, admission_policy=dict(policy, service_pending_limit=4))
        assert counts(store) == before
        assert store.service_state()["admission_policy"] == policy
    finally:
        store.close()


@pytest.mark.parametrize("field,value", [("budget_units", 1001), ("model", "live"),
                                         ("grader_digest", "0" * 64), ("execution_deadline", 1.0)])
def test_independent_catalog_identity_before_durable_acceptance(tmp_path, field, value):
    cfg = config(tmp_path)
    instance = service_for(cfg)
    store = RuntimeStore("sqlite:///" + str(tmp_path / "policy.sqlite"), admission_policy=cfg["admission_policy"])
    try:
        app = create_app(store, tokens=instance.tokens, contract_admission=instance.admission)
        with TestClient(app) as client:
            contract = dict(cfg["catalog"][0], **{field: value})
            response = client.post("/tasks", headers={"Authorization": "Bearer " + TOKEN},
                                   json={"key": "altered", "contract": contract})
            assert response.status_code == 422
            assert counts(store) == {"tasks": 0, "submissions": 0, "outbox": 0, "events": 0}
    finally:
        store.close()


def test_independent_ready_probe_is_read_only_and_checks_drift(tmp_path):
    cfg = config(tmp_path)
    with configured_service(cfg) as instance:
        before = instance.store.service_state()
        row_counts = counts(instance.store)
        assert instance.readiness()["ready"]
        assert instance.store.service_state() == before
        assert counts(instance.store) == row_counts
        sentinel = instance.artifacts._path(*SENTINEL_SCOPE, digest_bytes(SENTINEL))
        sentinel.write_bytes(b"independent corruption")
        assert not instance.readiness()["ready"]
        assert sentinel.read_bytes() == b"independent corruption"
        assert instance.store.service_state() == before
        with instance.store._tx() as (connection, guard):
            guard["tenant_slot_limit"] += 1
            connection.execute(authority.update().where(authority.c.id == 1).values(data=guard))
        changed = instance.store.service_state()
        assert not instance.readiness()["ready"]
        assert instance.store.service_state() == changed


@pytest.mark.parametrize("replacement_kind", ["missing", "empty"])
def test_independent_missing_authority_db_cannot_bootstrap_over_saved_identity(tmp_path, replacement_kind):
    cfg = config(tmp_path)
    with configured_service(cfg) as first:
        acknowledged = first.store.submit("review", "acknowledged", cfg["catalog"][0])
        task_id = acknowledged["task_id"]
    root = Path(cfg["root"])
    database = root / "authority.sqlite"
    preserved = root / "preserved-authority.sqlite"
    database.rename(preserved)
    if replacement_kind == "empty":
        database.write_bytes(b"")
    replacement = service_for(cfg)
    try:
        with pytest.raises(ValueError):
            replacement.start()
        assert (not database.exists()) if replacement_kind == "missing" else database.stat().st_size == 0
        saved = RuntimeStore("sqlite:///" + str(preserved))
        try:
            assert saved.get_task("review", task_id)["task_id"] == task_id
        finally:
            saved.close()
    finally:
        replacement.stop()


def test_independent_replaced_valid_database_cannot_reuse_saved_root_identity(tmp_path):
    cfg = config(tmp_path)
    with configured_service(cfg) as original:
        original_incarnation = original.incarnation
    root = Path(cfg["root"])
    database = root / "authority.sqlite"
    database.rename(root / "preserved-authority.sqlite")
    # A well-formed empty database passes ordinary schema/policy checks.
    other = RuntimeStore("sqlite:///" + str(database), **cfg["limits"], admission_policy=cfg["admission_policy"])
    try:
        assert other.service_state()["service_incarnation"] != original_incarnation
        marker = (root / "service-identity.json").read_bytes()
        replacement = service_for(cfg)
        try:
            with pytest.raises(ValueError):
                replacement.start()
            assert (root / "service-identity.json").read_bytes() == marker
            assert counts(other) == {"tasks": 0, "submissions": 0, "outbox": 0, "events": 0}
        finally:
            replacement.stop()
    finally:
        other.close()


def test_independent_worker_kill_retains_unknown_and_restart_refuses(tmp_path):
    cfg = config(tmp_path)
    instance = service_for(cfg)
    instance.start()
    stopped = False
    try:
        os.kill(instance.worker.pid, signal.SIGSTOP)
        stopped = True
        task = instance.store.submit("review", "active", cfg["catalog"][0])
        instance.store.set_graph("review", task["task_id"], 1, [{"node_id": "controlled"}])
        owner = instance.store.claim("review", task["task_id"], "controlled", "claim", 40, 300)["owner"]
        instance.store.begin_dispatch(owner, "model", "independent-unknown", "model", "a" * 64, 12)
        instance.store.finish_dispatch("review", "independent-unknown", "loss", "unknown")
        before = instance.store.snapshot("review", task["task_id"])
        os.kill(instance.worker.pid, signal.SIGKILL)
        stopped = False
        instance.worker.wait(timeout=5)
        eventually(lambda: not instance.store.service_state()["accept_new_tasks"])
        assert not instance.readiness()["ready"]
        assert instance.store.snapshot("review", task["task_id"]) == before
    finally:
        if stopped and instance.worker.poll() is None:
            os.kill(instance.worker.pid, signal.SIGCONT)
        instance.stop()
    restored = service_for(cfg)
    try:
        with pytest.raises(ValueError, match="reconciliation_required"):
            restored.start()
        saved = RuntimeStore("sqlite:///" + str(Path(cfg["root"]) / "authority.sqlite"))
        try:
            assert saved.snapshot("review", task["task_id"]) == before
        finally:
            saved.close()
    finally:
        restored.stop()


@contextmanager
def http_process(cfg, tmp_path):
    cfg_path = tmp_path / "http-config.json"
    cfg_path.write_bytes(canonical_bytes(cfg))
    env = dict(os.environ)
    env["CAM_SERVE_TOKEN_REVIEW"] = TOKEN
    process = subprocess.Popen([sys.executable, "-I", "-m", "service.offline_server", "serve", "--config", str(cfg_path)],
                               env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    client = httpx.Client(base_url=f"http://127.0.0.1:{cfg['port']}", timeout=2, trust_env=False)
    try:
        def ready():
            if process.poll() is not None:
                raise AssertionError("owned service exited during startup")
            try:
                return client.get("/ready").status_code == 200
            except httpx.TransportError:
                return False
        eventually(ready)
        yield process, client
    finally:
        client.close()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_independent_real_http_clean_restart_identity_events_and_artifacts(tmp_path):
    cfg = config(tmp_path)
    headers = {"Authorization": "Bearer " + TOKEN}
    with http_process(cfg, tmp_path) as (first, client):
        assert client.get("/catalog").status_code == 401
        contract = client.get("/catalog", headers=headers).json()["contracts"][0]
        response = client.post("/tasks", headers=headers, json={"key": "stable", "contract": contract})
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        eventually(lambda: client.get("/tasks/" + task_id, headers=headers).json()["execution_state"] == "review_eligible")
        snapshot = client.get(f"/tasks/{task_id}/snapshot", headers=headers).json()
        assert snapshot["task"]["review_state"] == "pending"
        events = client.get(f"/tasks/{task_id}/events", headers=headers).json()["events"]
        assert events and events[0]["sequence"] == 1
        ref = snapshot["candidates"][0]["manifest"]["artifact_ref"]
        artifact = client.get(f"/tasks/{task_id}/artifacts/{ref['digest']}", headers=headers)
        assert artifact.status_code == 200 and digest_bytes(artifact.content) == ref["digest"]
        replay = client.post("/tasks", headers=headers, json={"key": "stable", "contract": contract})
        assert replay.status_code == 202 and replay.json()["task_id"] == task_id
    # Uvicorn deliberately re-raises its captured SIGTERM after lifespan cleanup.
    assert first.returncode in {0, -signal.SIGTERM}
    saved = RuntimeStore("sqlite:///" + str(Path(cfg["root"]) / "authority.sqlite"))
    try:
        assert not saved.service_state()["accept_new_tasks"]
        assert saved.get_task("review", task_id)["execution_state"] == "review_eligible"
    finally:
        saved.close()
    with http_process(cfg, tmp_path) as (second, client):
        assert second.pid != first.pid
        replay = client.post("/tasks", headers=headers, json={"key": "stable", "contract": contract})
        assert replay.status_code == 202 and replay.json()["task_id"] == task_id
        assert client.get(f"/tasks/{task_id}", headers=headers).json()["review_state"] == "pending"


def test_independent_http_backpressure_does_not_reject_identical_retry(tmp_path):
    cfg = config(tmp_path)
    with configured_service(cfg) as instance:
        os.kill(instance.worker.pid, signal.SIGSTOP)
        try:
            app = create_app(instance.store, tokens=instance.tokens, contract_admission=instance.admission)
            with TestClient(app) as client:
                headers = {"Authorization": "Bearer " + TOKEN}
                payload = {"key": "one", "contract": cfg["catalog"][0]}
                first = client.post("/tasks", headers=headers, json=payload)
                assert first.status_code == 202
                task_id = first.json()["task_id"]
                before = counts(instance.store)
                assert client.post("/tasks", headers=headers, json=dict(payload, key="two")).status_code == 429
                repeated = client.post("/tasks", headers=headers, json=payload)
                assert repeated.status_code == 202 and repeated.json()["task_id"] == task_id
                assert counts(instance.store) == before
        finally:
            os.kill(instance.worker.pid, signal.SIGCONT)
        eventually(lambda: instance.store.get_task("review", task_id)["execution_state"] == "review_eligible")
        assert instance.store.submit("review", "two", cfg["catalog"][0])["task_id"] != task_id


def test_independent_parent_death_keeps_lock_until_owned_child_stops(tmp_path):
    cfg = config(tmp_path)
    cfg_path = tmp_path / "parent-config.json"
    cfg_path.write_bytes(canonical_bytes(cfg))
    helper = (
        "import json,os,sys,time; from service.offline_server import OfflineService; "
        "from service.serving_config import read_json_file,load_tokens; "
        "c=read_json_file(sys.argv[1]); s=OfflineService(c,load_tokens(c,os.environ)); "
        "s.start(); print(json.dumps({'child':s.worker.pid}),flush=True); time.sleep(60)"
    )
    env = dict(os.environ)
    env["CAM_SERVE_TOKEN_REVIEW"] = TOKEN
    parent = subprocess.Popen([sys.executable, "-I", "-c", helper, str(cfg_path)], env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              start_new_session=True)
    child = None
    try:
        import select
        assert select.select([parent.stdout], [], [], 20)[0], "owned parent failed to announce child"
        child = json.loads(parent.stdout.readline())["child"]
        os.kill(child, signal.SIGSTOP)
        parent.kill()
        parent.wait(timeout=5)
        lock = os.open(Path(cfg["root"]) / "service.lock", os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.kill(child, signal.SIGCONT)

            def lock_released():
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except BlockingIOError:
                    return False
            eventually(lock_released)
            fcntl.flock(lock, fcntl.LOCK_UN)
        finally:
            os.close(lock)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        parent.stdout.close()
        if child is not None:
            try:
                os.kill(child, signal.SIGCONT)
            except ProcessLookupError:
                pass
