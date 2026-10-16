"""Author controls for exact policy and journaled source identity."""
import hashlib
from pathlib import Path

import pytest

from service.environment_recovery import DockerEnvironmentBackend
from service.execution import DockerSandbox
from service.verification import LinuxVerifier, RPC_SOURCE
from test_environment_recovery import case, instance as admit, journal, FakeDocker, observation, IMAGE, CID, REJECT, started


@pytest.mark.parametrize("key,value", [
    ("CapAdd", ["SYS_ADMIN"]), ("Devices", [{"PathOnHost": "/dev/fake"}]),
    ("DeviceRequests", [{"Driver": "nvidia"}]), ("VolumesFrom", ["other"]),
    ("PidMode", "host"), ("IpcMode", "host"), ("UsernsMode", "host"),
    ("CgroupnsMode", "host"), ("UTSMode", "host"), ("ExtraHosts", ["host:127.0.0.1"]),
    ("PortBindings", {"80/tcp": [{"HostPort": "8080"}]}), ("Links", ["other"]),
])
def test_added_permissions_or_host_namespaces_never_bind_or_delete(tmp_path, key, value):
    from service.environment_recovery import reconcile_environment
    c = case(tmp_path)
    binding = admit(c)
    c.fake.install(binding.instance)["HostConfig"][key] = value
    before = c.store.snapshot(c.task["tenant_id"], c.task["task_id"])["budget"]
    result = reconcile_environment(c.lifecycle)
    assert result["status"] == "unresolved"
    assert CID in c.fake.containers
    assert not any(args[1] == "rm" for args, _ in c.fake.commands)
    assert c.store.snapshot(c.task["tenant_id"], c.task["task_id"])["budget"] == before
    assert journal(c)["instances"][0]["state"] == "create_intent"


@pytest.mark.parametrize("endpoint", ["tcp://127.0.0.1:2375", "ssh://localhost", "npipe:////./pipe/docker_engine"])
def test_remote_or_non_unix_backend_refused_before_creation(monkeypatch, endpoint):
    fake = FakeDocker()
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setenv("DOCKER_HOST", endpoint)
    with pytest.raises(RuntimeError, match="identity"):
        DockerEnvironmentBackend("author-local", runner=fake)
    assert fake.effects == []


def test_linux_source_identity_independently_matches_exact_source_bytes(monkeypatch):
    import service.verification as verification
    import service.execution as execution
    from service.artifacts import digest_json
    monkeypatch.setattr(verification, "bounded_process", lambda *a, **k: observation((IMAGE + " arm64 linux").encode()))
    actual = LinuxVerifier(IMAGE)
    expected = {"schema": 1, "image": IMAGE, "image_config_id": IMAGE, "architecture": "arm64", "os": "linux",
                "network": "none", "memory_mb": 192, "cpus": .5, "pids": 32, "disk_mb": 16,
                "rpc": digest_json(RPC_SOURCE),
                "controller": hashlib.sha256(Path(verification.__file__).read_bytes()).hexdigest(),
                "execution": hashlib.sha256(Path(execution.__file__).read_bytes()).hexdigest()}
    assert actual.environment_digest == digest_json(expected)


def test_durable_nonce_is_used_exactly_on_actual_sandbox_path(tmp_path):
    c = case(tmp_path)
    binding = admit(c)
    c.fake.on_create = lambda argv: c.fake.install(binding.instance)
    # FakeDocker's no-fault create deliberately needs an explicit acknowledged fixture response.
    c.fake.create_fault = observation((CID + "\n").encode())
    sandbox = DockerSandbox(IMAGE, journal_binding=binding)
    sandbox.start(c.files)
    create = next(args for args, _ in c.fake.commands if args[1] == "create")
    assert "coding-agent-mastery-create-nonce=" + binding.instance["creation_nonce"] in create
    assert create[create.index("--name") + 1] == binding.instance["name"]
    assert sandbox.close()["retired"] is True
    c.lifecycle.close()


def test_incarnation_changed_at_last_daemon_preflight_retains_original_instance(tmp_path, monkeypatch):
    c = case(tmp_path)
    sandbox = started(c)
    inspect, confirm = c.backend.inspect_owned, c.backend.confirm
    completed = {"inspection": False, "intervened": False}

    def inspected(instance):
        result = inspect(instance)
        completed["inspection"] = True
        return result

    def daemon_preflight(expected):
        result = confirm(expected)
        if completed["inspection"] and not completed["intervened"]:
            c.store.quarantine_restore("author-replaced-incarnation", {"backup": "author-disposable-control"})
            completed["intervened"] = True
        return result

    monkeypatch.setattr(c.backend, "inspect_owned", inspected)
    monkeypatch.setattr(c.backend, "confirm", daemon_preflight)
    before = list(c.fake.effects)
    with pytest.raises(REJECT):
        sandbox.close()
    assert completed["intervened"] and c.fake.effects == before
    assert CID in c.fake.containers
