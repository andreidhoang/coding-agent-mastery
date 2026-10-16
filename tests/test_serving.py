"""Configured offline serving and transactional admission controls."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import socket
import threading
import time

import pytest
from fastapi.testclient import TestClient

from service.artifacts import LocalArtifacts
from service.contracts import CapacityExceeded, Conflict, Unsupported
from service.offline_server import OfflineService, SENTINEL, SENTINEL_SCOPE, _startup_frontier
from service.serving_config import fixture_contract, load_tokens, validate_config
from service.storage import RuntimeStore
from workloads import list_tasks

TOKEN = "synthetic-offline-serving-test-credential"


def config_for(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    contract = fixture_contract(list_tasks(tier="T1")[0].task_id, time.time() + 600, time.time() + 3600)
    return {
        "schema": 1,
        "mode": "offline_fixture_v1",
        "root": str(tmp_path / "runtime"),
        "host": "127.0.0.1",
        "port": port,
        "limits": {
            "service_slot_limit": 3,
            "tenant_slot_limit": 3,
            "service_budget_units": 100000,
            "tenant_budget_units": 100000,
        },
        "admission_policy": {"schema": 1, "service_pending_limit": 2, "tenant_pending_limit": 1},
        "worker": {"poll_ms": 100, "shutdown_seconds": 3},
        "principals": [
            {
                "tenant_id": "demo",
                "subject_id": "operator",
                "can_review": True,
                "repositories": [contract["repo_id"]],
                "profiles": ["production"],
                "token_env": "CAM_SERVE_TOKEN_LOCAL",
            }
        ],
        "catalog": [contract],
    }


def simple_contract():
    return {"repo_id": "fixture", "base_revision": "baseline", "requirements": ["exercise admission"]}


def test_pending_caps_retry_cancel_and_persisted_omission(tmp_path):
    url = "sqlite:///" + str(tmp_path / "authority.sqlite")
    policy = {"schema": 1, "service_pending_limit": 2, "tenant_pending_limit": 1}
    with_store = RuntimeStore(url, admission_policy=policy)
    other = RuntimeStore(url)
    try:
        first = with_store.submit("a", "one", simple_contract())
        before = with_store.list_outbox()
        assert other.submit("a", "one", simple_contract())["task_id"] == first["task_id"]
        with pytest.raises(CapacityExceeded):
            other.submit("a", "two", simple_contract())
        with pytest.raises(Conflict):
            other.submit("a", "one", dict(simple_contract(), requirements=["different"]))
        assert with_store.list_outbox() == before
        with_store.submit("b", "one", simple_contract())
        with pytest.raises(CapacityExceeded):
            other.submit("c", "one", simple_contract())
        with_store.set_graph("a", first["task_id"], 1, [{"node_id": "n"}])
        owner = with_store.claim("a", first["task_id"], "n", "claim", 40, 300)["owner"]
        with_store.begin_dispatch(owner, "act", "dispatch", "model", "0" * 64, 12)
        with_store.cancel("a", first["task_id"], "cancel")
        other.submit("a", "two", simple_contract())
        old = other.snapshot("a", first["task_id"])
        assert old["budget"]["reserved"] == 40
        assert old["sandboxes"][0]["status"] != "retired"
        with_store.set_admission(False)
        assert other.submit("a", "one", simple_contract())["task_id"] == first["task_id"]
    finally:
        with_store.close()
        other.close()


def test_atomic_final_pending_slot_two_connections(tmp_path):
    url = "sqlite:///" + str(tmp_path / "authority.sqlite")
    policy = {"schema": 1, "service_pending_limit": 1, "tenant_pending_limit": 1}
    stores = [RuntimeStore(url, admission_policy=policy), RuntimeStore(url, admission_policy=policy)]
    barrier = threading.Barrier(2)

    def submit(index):
        barrier.wait()
        try:
            return stores[index].submit("tenant", "key" + str(index), simple_contract())["task_id"]
        except CapacityExceeded:
            return None

    try:
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(submit, (0, 1)))
        assert len([result for result in results if result]) == 1
        assert len(stores[0].list_outbox()) == 1
    finally:
        for store in stores:
            store.close()


@pytest.mark.parametrize("change", ["schema", "bool", "zero", "oversized", "tenant", "extra"])
def test_policy_strictness(tmp_path, change):
    policy = {"schema": 1, "service_pending_limit": 2, "tenant_pending_limit": 1}
    if change == "schema":
        policy["schema"] = True
    elif change == "bool":
        policy["service_pending_limit"] = True
    elif change == "zero":
        policy["service_pending_limit"] = 0
    elif change == "oversized":
        policy["service_pending_limit"] = 10001
    elif change == "tenant":
        policy["tenant_pending_limit"] = 3
    else:
        policy["extra"] = 0
    with pytest.raises(ValueError):
        RuntimeStore("sqlite:///" + str(tmp_path / "invalid.sqlite"), admission_policy=policy)
    assert not (tmp_path / "invalid.sqlite").exists()


def test_explicit_policy_cannot_change_existing_store(tmp_path):
    url = "sqlite:///" + str(tmp_path / "authority.sqlite")
    store = RuntimeStore(url)
    store.close()
    policy = {"schema": 1, "service_pending_limit": 2, "tenant_pending_limit": 1}
    with pytest.raises(Unsupported):
        RuntimeStore(url, admission_policy=policy)
    other_url = "sqlite:///" + str(tmp_path / "configured.sqlite")
    RuntimeStore(other_url, admission_policy=policy).close()
    with pytest.raises(Unsupported):
        RuntimeStore(other_url, admission_policy=dict(policy, tenant_pending_limit=2))


@pytest.mark.parametrize(
    "fault",
    [
        "host",
        "port",
        "mode",
        "extra",
        "token",
        "principal",
        "catalog",
        "model",
        "grader",
        "deadline",
        "capability",
        "limits",
        "worker",
        "root",
    ],
)
def test_closed_configuration_rejects_unsupported_surface(tmp_path, fault):
    config = config_for(tmp_path)
    if fault == "host":
        config["host"] = "0.0.0.0"
    elif fault == "port":
        config["port"] = True
    elif fault == "mode":
        config["mode"] = "live"
    elif fault == "extra":
        config["command"] = "echo invalid"
    elif fault == "token":
        config["principals"][0]["token_env"] = "OPENAI_API_KEY"
    elif fault == "principal":
        config["principals"].append(deepcopy(config["principals"][0]))
    elif fault == "catalog":
        config["catalog"].append(deepcopy(config["catalog"][0]))
    elif fault == "model":
        config["catalog"][0]["model"] = "live-model"
    elif fault == "grader":
        config["catalog"][0]["grader_digest"] = "0" * 64
    elif fault == "deadline":
        config["catalog"][0]["execution_deadline"] = True
    elif fault == "capability":
        config["catalog"][0]["capabilities"].append("shell")
    elif fault == "limits":
        config["limits"]["tenant_slot_limit"] = 0
    elif fault == "worker":
        config["worker"]["poll_ms"] = False
    else:
        config["root"] = "relative/path"
    with pytest.raises(ValueError):
        validate_config(config)
    assert not (tmp_path / "runtime").exists()


def test_credential_and_symlink_refusal(tmp_path):
    config = config_for(tmp_path)
    with pytest.raises(ValueError):
        load_tokens(config, {})
    with pytest.raises(ValueError):
        load_tokens(config, {"CAM_SERVE_TOKEN_LOCAL": "short"})
    original = tmp_path / "original"
    original.mkdir()
    (tmp_path / "runtime").symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError):
        validate_config(config)


def test_configured_service_worker_lifecycle_and_clean_restart(tmp_path):
    config = config_for(tmp_path)
    tokens = load_tokens(config, {"CAM_SERVE_TOKEN_LOCAL": TOKEN})
    headers = {"Authorization": "Bearer " + TOKEN}
    first = OfflineService(config, tokens)
    with TestClient(first.app()) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/catalog").status_code == 401
        contract = client.get("/catalog", headers=headers).json()["contracts"][0]
        rejected = dict(contract, requirements=["different same repository"])
        assert (
            client.post("/tasks", headers=headers, json={"key": "bad", "contract": rejected}).status_code
            == 422
        )
        assert first.store.list_outbox() == []
        result = client.post("/tasks", headers=headers, json={"key": "work", "contract": contract})
        assert result.status_code == 202
        task = result.json()["task_id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = client.get("/tasks/" + task, headers=headers).json()
            if state["execution_state"] == "review_eligible":
                break
            time.sleep(0.05)
        assert state["execution_state"] == "review_eligible" and state["review_state"] == "pending"
        assert (
            client.post("/tasks", headers=headers, json={"key": "work", "contract": contract}).json()[
                "task_id"
            ]
            == task
        )
        second = OfflineService(config, tokens)
        with pytest.raises(BlockingIOError):
            second.start()
        assert first.readiness()["ready"]
        assert all(name not in first.worker.args for name in (TOKEN, "OPENAI_API_KEY"))
        assert TOKEN.encode() not in (first.root / "worker-config.json").read_bytes()
    assert first.worker.poll() == 0
    restarted = OfflineService(config, tokens)
    with TestClient(restarted.app()) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/tasks/" + task, headers=headers).json()["execution_state"] == "review_eligible"
        assert (
            client.post("/tasks", headers=headers, json={"key": "work", "contract": contract}).json()[
                "task_id"
            ]
            == task
        )


def test_readiness_detects_artifact_and_worker_failure_without_repair(tmp_path):
    from service.artifacts import digest_bytes

    config = config_for(tmp_path)
    service = OfflineService(config, load_tokens(config, {"CAM_SERVE_TOKEN_LOCAL": TOKEN}))
    with TestClient(service.app()) as client:
        sentinel = service.artifacts._path(*SENTINEL_SCOPE, digest_bytes(SENTINEL))
        sentinel.write_bytes(b"damaged")
        assert client.get("/ready").status_code == 503
        assert sentinel.read_bytes() == b"damaged"
        assert client.get("/health").status_code == 200
        service.worker.terminate()
        service.worker.wait(timeout=5)
        assert client.get("/ready").status_code == 503


def test_startup_refuses_retained_effect_and_physical_frontier(tmp_path):
    config = config_for(tmp_path)
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore(
        "sqlite:///" + str(tmp_path / "authority.sqlite"),
        artifacts,
        **config["limits"],
        admission_policy=config["admission_policy"],
    )
    task = store.submit("demo", "queued", config["catalog"][0])
    _startup_frontier(store, config)
    store.set_graph("demo", task["task_id"], 1, [{"node_id": "n"}])
    owner = store.claim("demo", task["task_id"], "n", "claim", 40, 300)["owner"]
    store.begin_dispatch(owner, "a", "d", "model", "0" * 64, 12)
    before = store.snapshot("demo", task["task_id"])
    with pytest.raises(ValueError, match="reconciliation_required"):
        _startup_frontier(store, config)
    assert store.snapshot("demo", task["task_id"]) == before
    store.close()


@pytest.mark.parametrize("fault", ["policy_missing", "digest_missing", "null", "digest_wrong"])
def test_corrupt_persisted_policy_rejects_admission_and_reopen(tmp_path, fault):
    from service.storage import authority
    import sqlalchemy as sa
    url = "sqlite:///" + str(tmp_path / "authority.sqlite")
    policy = {"schema": 1, "service_pending_limit": 2, "tenant_pending_limit": 1}
    store = RuntimeStore(url, admission_policy=policy)
    try:
        with store._tx() as (connection, guard):
            if fault == "policy_missing":
                guard.pop("admission_policy")
            elif fault == "digest_missing":
                guard.pop("admission_policy_digest")
            elif fault == "null":
                guard["admission_policy"] = None
            else:
                guard["admission_policy_digest"] = "0" * 64
            connection.execute(sa.update(authority).where(authority.c.id == 1).values(data=guard))
        with pytest.raises(Unsupported):
            store.submit("a", "key", simple_contract())
        with pytest.raises(Unsupported):
            RuntimeStore(url)
    finally:
        store.close()


def test_credentials_cannot_override_frozen_principal_map(tmp_path):
    config = config_for(tmp_path)
    tokens = load_tokens(config, {"CAM_SERVE_TOKEN_LOCAL": TOKEN})
    with pytest.raises(ValueError):
        OfflineService(config, {})
    with pytest.raises(ValueError):
        OfflineService(config, {"short": next(iter(tokens.values()))})
    from service.api import Principal
    with pytest.raises(ValueError):
        OfflineService(config, {TOKEN: Principal("foreign", "operator", frozenset({"ungranted"}))})
    assert not (tmp_path / "runtime").exists()


@pytest.mark.parametrize("suffix", ["?query", "#fragment", "\nline"])
def test_root_cannot_change_sqlite_url_meaning(tmp_path, suffix):
    config = config_for(tmp_path)
    config["root"] += suffix
    with pytest.raises(ValueError):
        validate_config(config)
