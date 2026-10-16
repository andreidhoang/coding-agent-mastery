"""Independent E01–E12 physical ownership oracles from the frozen contract.

FakeDocker models physical state separately from authority rows. It deliberately
supports delayed create, name reuse, bad daemon identity and incomplete output.
Real Docker checks use only an explicitly configured, already cached image.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import uuid

import pytest
import sqlalchemy as sa

from service.artifacts import LocalArtifacts
from service.contracts import RuntimeErrorBase
from service.execution import DockerSandbox, bounded_process, tree_digest
from service.storage import RuntimeStore


IMAGE = "sha256:" + "a" * 64
CID = "b" * 64
REJECT = (ValueError, PermissionError, RuntimeError, RuntimeErrorBase)
FILES = {"calc.py": "def add(a, b): return a + b\n"}
JOURNAL_KEYS = set("schema profile revision phase backend source max_instances instances".split())
INSTANCE_KEYS = set("ordinal intent_id name creation_nonce launch state container_id create_observation_ref retirement_observation_ref".split())
SOURCE_KEYS = set("generation service_incarnation purpose tree_digest input_digest grader_digest environment_digest".split())
LAUNCH_KEYS = set("image memory_mb cpus pids disk_mb timeout_seconds policy_digest".split())
FROZEN_POLICY = {"schema": 1, "pull": "never", "network": "none", "read_only": True,
    "user": "65534:65534", "cap_drop": ["ALL"], "security_opt": ["no-new-privileges"],
    "host_mounts": [], "memory_swap_equals_memory": True, "ulimits": {"nofile": 128, "fsize": 8388608},
    "log_driver": "none", "workspace": "rw,nosuid,nodev,size={disk_mb}m,mode=1777",
    "tmp": "rw,noexec,nosuid,nodev,size=8m,mode=1777", "workdir": "/workspace",
    "entrypoint": ["python"], "command": ["-I", "-c", "import time; time.sleep(3600)"]}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def observation(output=b"", **changes):
    return {"exit_code": 0, "reason": "exited", "output": output,
        "duration_seconds": 0.01, "process_group_retired": True, "truncated": False, **changes}


class FakeDocker:
    def __init__(self):
        self.daemon = "independent-daemon-7a1f"
        self.containers = {}
        self.commands = []
        self.create_fault = None
        self.probe_fault = None
        self.start_fault = None
        self.copy_fault = None
        self.run_fault = None
        self.remove_fault = None
        self.hidden = False
        self.on_create = None
        self.inspection_change = None

    def install(self, instance, *, cid=CID, image=IMAGE, **changes):
        launch = instance["launch"]
        details = {"Id": cid, "Name": "/" + instance["name"], "Image": image,
            "Config": {"Image": image, "Labels": {"coding-agent-mastery": "disposable",
                "coding-agent-mastery-create-nonce": instance["creation_nonce"]},
                "User": "65534:65534", "WorkingDir": "/workspace", "Entrypoint": ["python"],
                "Cmd": ["-I", "-c", "import time; time.sleep(3600)"]},
            "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True,
                "Privileged": False, "Binds": None, "CapDrop": ["ALL"],
                "CapAdd": None, "Devices": [], "DeviceRequests": None, "VolumesFrom": None,
                "PidMode": "", "IpcMode": "private", "UsernsMode": "", "CgroupnsMode": "private",
                "UTSMode": "", "ExtraHosts": None, "PortBindings": {}, "Links": None,
                "SecurityOpt": ["no-new-privileges"], "Memory": launch["memory_mb"] * 1024 * 1024,
                "MemorySwap": launch["memory_mb"] * 1024 * 1024,
                "NanoCpus": int(launch["cpus"] * 1_000_000_000), "PidsLimit": launch["pids"],
                "LogConfig": {"Type": "none", "Config": {}},
                "Tmpfs": {"/workspace": f"rw,nosuid,nodev,size={launch['disk_mb']}m,mode=1777",
                    "/tmp": "rw,noexec,nosuid,nodev,size=8m,mode=1777"},
                "Ulimits": [{"Name": "nofile", "Soft": 128, "Hard": 128},
                    {"Name": "fsize", "Soft": 8388608, "Hard": 8388608}]},
            "Mounts": [], "State": {"Running": False}}
        details.update(changes)
        self.containers[cid] = details
        return details

    def __call__(self, argv, **kwargs):
        self.commands.append((list(argv), dict(kwargs)))
        assert argv[0] == "docker", "Only fixed Docker commands reach this runner"
        if argv[1] == "info":
            return observation((self.daemon + "\n").encode())
        if argv[1:3] == ["context", "inspect"]:
            return observation(canonical({"Name": "independent-local", "Endpoints": {
                "docker": {"Host": "unix:///independent/docker.sock", "SkipTLSVerify": False}}}))
        if argv[1:3] == ["image", "inspect"]:
            return observation((IMAGE + (" arm64 linux\n" if "Architecture" in argv[-1] else "\n")).encode())
        if argv[1] == "create":
            if self.on_create:
                self.on_create(argv)
            if self.create_fault:
                return self.create_fault
            raise AssertionError("Fake create requires independent journal-aware hook")
        if argv[1] == "inspect":
            details = self.containers.get(argv[2])
            if details is None:
                return observation(b"No such container", exit_code=1)
            details = deepcopy(details)
            if self.inspection_change:
                self.inspection_change(details)
            return observation(canonical(details))
        if argv[1] == "ps":
            assert "--filter" in argv and "--no-trunc" in argv
            assert kwargs.get("max_output") == 132 and kwargs.get("timeout") == 30
            selector = argv[argv.index("--filter") + 1]
            if self.probe_fault:
                return self.probe_fault
            if self.hidden:
                return observation()
            if selector.startswith("label=coding-agent-mastery-create-nonce="):
                nonce = selector.split("=", 2)[-1]
                matches = [cid for cid, value in self.containers.items()
                    if value["Config"]["Labels"].get("coding-agent-mastery-create-nonce") == nonce]
            elif selector.startswith("id="):
                matches = [cid for cid in self.containers if cid == selector[3:]]
            else:
                raise AssertionError("Unbounded or name-only inventory is forbidden")
            return observation(("\n".join(matches) + ("\n" if matches else "")).encode())
        if argv[1] == "rm":
            assert argv[-1] in self.containers or len(argv[-1]) == 64, "Removal must use immutable ID"
            if self.remove_fault:
                return self.remove_fault
            self.containers.pop(argv[-1], None)
            return observation((argv[-1] + "\n").encode())
        if argv[1] == "start":
            return self.start_fault or observation((argv[2] + "\n").encode())
        if argv[1] == "exec":
            return self.copy_fault if "-i" in argv and self.copy_fault else self.run_fault or observation()
        raise AssertionError("Unexpected Docker operation: " + str(argv))

    @property
    def effects(self):
        return [args for args, _ in self.commands if args[1] in {"create", "start", "exec", "rm"}]


def case(path, *, url=None, fake=None, grader=None, environment=None, files=None):
    from service.environment_recovery import DockerEnvironmentBackend, EnvironmentLifecycle, launch_value
    artifacts = LocalArtifacts(path / "artifacts")
    store = RuntimeStore(url or "sqlite:///" + str(path / "runtime.db"), artifacts,
        service_slot_limit=4, tenant_slot_limit=4)
    files = dict(files or FILES)
    task = store.submit("environment-tenant", "environment-case", {
        "repo_id": "trusted-environment-fixture", "base_revision": tree_digest(files),
        "requirements": ["Bound physical cleanup to the original creation intention"],
        **({"grader_digest": grader} if grader else {}),
        **({"environment_digest": environment} if environment else {})})
    reservation = store.reserve_environment(task["tenant_id"], task["task_id"], 1, "verifier", "verification")
    fake = fake or FakeDocker()
    backend = DockerEnvironmentBackend("independent-local-docker", runner=fake)
    lifecycle = EnvironmentLifecycle(store, artifacts, task["tenant_id"], task["task_id"], reservation["sandbox_id"], backend)
    source = {"generation": 1, "service_incarnation": store.execution_incarnation, "purpose": "fixture",
        "tree_digest": tree_digest(files), "input_digest": digest(files),
        "grader_digest": task["contract"]["grader_digest"], "environment_digest": task["contract"]["environment_digest"]}
    launch = launch_value(IMAGE, memory_mb=192, cpus=0.5, pids=32, disk_mb=16, timeout=20)
    return SimpleNamespace(store=store, artifacts=artifacts, task=task, reservation=reservation,
        lifecycle=lifecycle, backend=backend, fake=fake, source=source, launch=launch, path=path, files=files)


def journal(c):
    return c.store.read_environment_journal(c.task["tenant_id"], c.reservation["sandbox_id"])["environment_journal"]


def snapshot(c):
    return c.store.snapshot(c.task["tenant_id"], c.task["task_id"])


def instance(c, ordinal=0, max_instances=1, **changes):
    return c.lifecycle.instance(ordinal=ordinal, source=c.source,
        launch={**c.launch, **changes}, max_instances=max_instances)


def reconcile(c):
    from service.environment_recovery import reconcile_environment
    return reconcile_environment(c.lifecycle, c.backend)


def started(c, *, max_instances=1, ordinal=0):
    binding = instance(c, ordinal, max_instances)
    def created(argv):
        saved = journal(c)
        row = saved["instances"][ordinal]
        assert row["state"] == "create_intent" and row["container_id"] is None
        assert argv[argv.index("--name") + 1] == row["name"]
        assert "coding-agent-mastery-create-nonce=" + row["creation_nonce"] in argv
        c.fake.install(row)
    c.fake.on_create = created
    c.fake.create_fault = observation((CID + "\n").encode())
    sandbox = DockerSandbox(IMAGE, journal_binding=binding)
    sandbox.start(c.files)
    return sandbox


def test_E01_exact_write_ahead_identity_and_immutable_nonce(tmp_path):
    c = case(tmp_path)
    binding = instance(c)
    saved = journal(c)
    assert set(saved) == JOURNAL_KEYS and saved["schema"] == 1
    assert saved["profile"] == "docker_environment_journal_v1" and saved["phase"] == "open"
    assert saved["revision"] == 1 and set(saved["source"]) == SOURCE_KEYS
    assert saved["source"] == c.source and saved["max_instances"] == 1
    row = saved["instances"][0]
    assert set(row) == INSTANCE_KEYS and set(row["launch"]) == LAUNCH_KEYS
    assert row["launch"]["policy_digest"] == digest(FROZEN_POLICY)
    assert row["intent_id"] == digest({"sandbox_id": c.reservation["sandbox_id"], "ordinal": 0,
        "source": c.source, "backend": saved["backend"], "launch": c.launch})
    assert len(row["creation_nonce"]) == 32 and int(row["creation_nonce"], 16) >= 0
    assert row["state"] == "create_intent" and row["container_id"] is None
    before = snapshot(c)
    repeated = instance(c)
    assert journal(c) == saved and snapshot(c) == before
    assert not c.fake.effects
    with pytest.raises(REJECT):
        DockerSandbox(IMAGE, journal_binding=repeated).start(FILES)
    assert not c.fake.effects
    assert binding is not None


@pytest.mark.parametrize("stage", ["before_commit", "lost_ack"])
def test_E01_journal_failure_or_lost_ack_never_creates(tmp_path, monkeypatch, stage):
    c = case(tmp_path)
    original = c.store.begin_environment_instance
    def fault(*a, **k):
        if stage == "lost_ack":
            original(*a, **k)
        raise RuntimeError("independent intent commit fault")
    monkeypatch.setattr(c.store, "begin_environment_instance", fault)
    with pytest.raises(RuntimeError, match="intent commit fault"):
        instance(c)
    assert not c.fake.effects
    monkeypatch.setattr(c.store, "begin_environment_instance", original)
    if stage == "lost_ack":
        nonce = journal(c)["instances"][0]["creation_nonce"]
        repeated = instance(c)
        with pytest.raises(REJECT):
            DockerSandbox(IMAGE, journal_binding=repeated).start(FILES)
        assert journal(c)["instances"][0]["creation_nonce"] == nonce and not c.fake.effects


def test_E02_zero_nonce_matches_stays_occupied_then_late_create_reconciles(tmp_path):
    c = case(tmp_path)
    instance(c)
    row = journal(c)["instances"][0]
    before = snapshot(c)
    result = reconcile(c)
    assert result["status"] == "unresolved"
    assert snapshot(c)["sandboxes"][0]["status"] != "retired"
    assert snapshot(c)["budget"] == before["budget"] and not c.fake.effects
    assert journal(c)["instances"][0]["state"] == "create_intent"
    assert journal(c)["phase"] == "cleanup_requested"
    c.fake.install(row)
    result = reconcile(c)
    assert result["status"] == "retired"
    assert [args[-1] for args in c.fake.effects] == [CID]
    assert journal(c)["instances"][0]["container_id"] == CID
    assert journal(c)["instances"][0]["state"] == "retired"
    assert journal(c)["phase"] == "retired" and snapshot(c)["sandboxes"][0]["status"] == "retired"


@pytest.mark.parametrize("fault", ["two_nonce_matches", "name", "nonce", "image", "network", "readonly", "user", "mount", "daemon", "id"])
def test_E03_wrong_physical_identity_never_binds_or_deletes(tmp_path, fault):
    c = case(tmp_path)
    instance(c)
    row = journal(c)["instances"][0]
    c.fake.install(row)
    if fault == "two_nonce_matches":
        c.fake.install(row, cid="c" * 64)
    elif fault == "daemon":
        c.fake.daemon = "different-daemon"
    elif fault == "nonce":
        c.fake.containers[CID]["Config"]["Labels"]["coding-agent-mastery-create-nonce"] = "f" * 32
    else:
        def change(details):
            if fault == "name":
                details["Name"] = "/reused-name"
            elif fault == "image":
                details["Image"] = "sha256:" + "d" * 64
            elif fault == "network":
                details["HostConfig"]["NetworkMode"] = "bridge"
            elif fault == "readonly":
                details["HostConfig"]["ReadonlyRootfs"] = False
            elif fault == "user":
                details["Config"]["User"] = "0:0"
            elif fault == "mount":
                details["Mounts"] = [{"Type": "bind", "Source": "/host", "Destination": "/workspace"}]
            else:
                details["Id"] = "e" * 64
        c.fake.inspection_change = change
    result = reconcile(c)
    assert result["status"] == "unresolved" and CID in c.fake.containers
    assert not c.fake.effects and journal(c)["instances"][0]["container_id"] is None
    assert snapshot(c)["sandboxes"][0]["status"] != "retired"


@pytest.mark.parametrize("incomplete", [{"reason": "timeout"}, {"truncated": True},
    {"process_group_retired": False}, {"exit_code": 1}, {"reason": "output_limit"}])
def test_E08_incomplete_inventory_never_releases_slot(tmp_path, incomplete):
    c = case(tmp_path)
    instance(c)
    c.fake.probe_fault = observation(**incomplete)
    assert reconcile(c)["status"] == "unresolved"
    assert snapshot(c)["sandboxes"][0]["status"] != "retired" and not c.fake.effects


def test_E03_bound_cleanup_uses_id_and_leaves_reused_name_untouched(tmp_path):
    c = case(tmp_path)
    sandbox = started(c)
    old = deepcopy(journal(c)["instances"][0])
    c.fake.containers.pop(CID)
    replacement = c.fake.install({**old, "creation_nonce": "f" * 32}, cid="c" * 64)
    assert replacement["Name"] == "/" + old["name"]
    result = reconcile(c)
    assert result["status"] == "retired" and "c" * 64 in c.fake.containers
    assert all(args[-1] != old["name"] and args[-1] != "c" * 64 for args in c.fake.effects if args[1] == "rm")
    assert sandbox.container_id == CID


def test_E06_per_case_retirement_then_final_cleanup_seals_admission(tmp_path):
    c = case(tmp_path)
    first = started(c, max_instances=2)
    with pytest.raises(REJECT):
        instance(c, 1, 2)
    assert first.close()["retired"] is True
    assert journal(c)["phase"] == "open" and journal(c)["instances"][0]["state"] == "retired"
    second = started(c, max_instances=2, ordinal=1)
    assert second.close()["retired"] is True
    assert reconcile(c)["status"] == "retired"
    before = snapshot(c)
    with pytest.raises(REJECT):
        instance(c, 2, 2)
    assert snapshot(c) == before and len([a for a in c.fake.effects if a[1] == "create"]) == 2


def test_E07_generic_retirement_cannot_bypass_unresolved_journal(tmp_path):
    c = case(tmp_path)
    instance(c)
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.store.retire_sandbox(c.task["tenant_id"], c.reservation["sandbox_id"],
            {"exit_observed": True, "supervisor": "fabricated-generic-proof"})
    assert snapshot(c) == before


def test_E05_cleanup_request_fences_start_copy_exec(tmp_path):
    c = case(tmp_path)
    sandbox = started(c)
    c.store.request_environment_cleanup(c.task["tenant_id"], c.reservation["sandbox_id"])
    before = len(c.fake.effects)
    with pytest.raises(REJECT):
        sandbox.run(["python", "-c", "print('must not execute')"])
    assert len(c.fake.effects) == before


def test_E12_unjournaled_reservation_is_explicitly_unsupported(tmp_path):
    c = case(tmp_path)
    before = snapshot(c)
    result = reconcile(c)
    assert result["status"] == "unsupported"
    assert snapshot(c) == before and not c.fake.effects
    assert "environment_journal" not in snapshot(c)["sandboxes"][0]


@pytest.mark.parametrize("stage", ["bind", "start", "copy"])
def test_E04_provision_failure_never_executes_without_durable_binding(tmp_path, monkeypatch, stage):
    c = case(tmp_path)
    if stage == "bind":
        original = c.store.bind_environment_instance
        def fail(*a, **k):
            raise RuntimeError("independent binding write failed")
        monkeypatch.setattr(c.store, "bind_environment_instance", fail)
    elif stage == "start":
        c.fake.start_fault = observation(b"start failed", exit_code=1)
        c.fake.remove_fault = observation(b"cleanup unavailable", exit_code=1)
    else:
        c.fake.copy_fault = observation(b"copy failed", exit_code=1)
        c.fake.remove_fault = observation(b"cleanup unavailable", exit_code=1)
    with pytest.raises(REJECT):
        started(c)
    row = journal(c)["instances"][0]
    assert row["state"] == ("create_intent" if stage == "bind" else "bound")
    assert len(c.fake.containers) == 1
    if stage == "bind":
        assert not any(args[1] in {"start", "exec"} for args in c.fake.effects)
        monkeypatch.setattr(c.store, "bind_environment_instance", original)
    if stage == "start":
        assert not any(args[1] == "exec" for args in c.fake.effects)
    c.fake.remove_fault = None
    assert reconcile(c)["status"] == "retired"


@pytest.mark.parametrize("result", [
    observation(b"unknown server error", exit_code=125),
    observation(b"", reason="timeout", exit_code=-9),
    observation((CID + "\n").encode(), truncated=True),
    observation(b"not-an-id\n"),
])
def test_E02_incomplete_create_remains_occupied_without_retry(tmp_path, result):
    c = case(tmp_path)
    binding = instance(c)
    c.fake.create_fault = result
    with pytest.raises(REJECT):
        DockerSandbox(IMAGE, journal_binding=binding).start(FILES)
    saved = journal(c)
    assert saved["instances"][0]["state"] == "create_intent"
    assert reconcile(c)["status"] == "unresolved"
    assert len([x for x in c.fake.effects if x[1] == "create"]) == 1
    assert snapshot(c)["sandboxes"][0]["status"] == "reserved"


def test_E02_zero_nonce_matches_cannot_claim_direct_retirement(tmp_path):
    c = case(tmp_path)
    binding = instance(c)
    before_budget = snapshot(c)["budget"]
    with pytest.raises(REJECT, match="unresolved"):
        binding.close()
    assert journal(c)["instances"][0]["state"] == "create_intent"
    assert snapshot(c)["sandboxes"][0]["status"] == "reserved"
    assert snapshot(c)["budget"] == before_budget and not c.fake.effects


@pytest.mark.parametrize("acknowledged", [True, False])
def test_E02_name_conflict_requires_complete_ack_and_never_removes_foreign_name(tmp_path, acknowledged):
    c = case(tmp_path)
    binding = instance(c)
    row = journal(c)["instances"][0]
    foreign = c.fake.install({**row, "creation_nonce": "f" * 32})
    c.fake.create_fault = observation(b"Conflict. The container name is already in use", exit_code=125,
        truncated=not acknowledged)
    with pytest.raises(REJECT):
        DockerSandbox(IMAGE, journal_binding=binding).start(FILES)
    saved = journal(c)["instances"][0]
    assert saved["state"] == ("create_rejected" if acknowledged else "create_intent")
    assert saved["container_id"] is None
    assert c.fake.containers[CID] == foreign
    assert not any(x[1] == "rm" for x in c.fake.effects)
    assert reconcile(c)["status"] == ("retired" if acknowledged else "unresolved")
    assert c.fake.containers[CID] == foreign


@pytest.mark.parametrize("field,value", [("CapAdd", ["SYS_ADMIN"]), ("Devices", [{"PathOnHost": "/dev/mem"}]),
    ("DeviceRequests", [{"Driver": "nvidia"}]), ("VolumesFrom", ["foreign"]), ("PidMode", "host"),
    ("IpcMode", "host"), ("UsernsMode", "host"), ("CgroupnsMode", "host"), ("UTSMode", "host"),
    ("ExtraHosts", ["example:127.0.0.1"]), ("PortBindings", {"80/tcp": [{"HostPort": "8080"}]}),
    ("Links", ["foreign:foreign"])])
def test_E03_recovery_refuses_host_capability_and_namespace_drift(tmp_path, field, value):
    c = case(tmp_path)
    instance(c)
    details = c.fake.install(journal(c)["instances"][0])
    details["HostConfig"][field] = value
    assert reconcile(c)["status"] == "unresolved"
    assert journal(c)["instances"][0]["state"] == "create_intent"
    assert not any(x[1] == "rm" for x in c.fake.effects)
    assert CID in c.fake.containers


def real_lifecycle(c, backend_id="real-local-test"):
    from service.environment_recovery import DockerEnvironmentBackend, EnvironmentLifecycle
    c.backend = DockerEnvironmentBackend(backend_id)
    c.lifecycle = EnvironmentLifecycle(c.store, c.artifacts, c.task["tenant_id"], c.task["task_id"],
        c.reservation["sandbox_id"], c.backend)
    return c.lifecycle


def cached_image():
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit cached Docker image required")
    return image


def test_E09_fixture_environment_binds_exact_controller_source_and_preserves_old_contract(tmp_path, monkeypatch):
    import service.verification as verification
    from service.engine import ReferenceEngine
    from workloads import list_tasks
    resolved_id = "sha256:" + "e" * 64
    def resolve(argv, **options):
        assert argv[:3] == ["docker", "image", "inspect"]
        return observation((resolved_id + " arm64 linux\n").encode())
    monkeypatch.setattr(verification, "bounded_process", resolve)
    verifier = verification.LinuxVerifier(IMAGE)
    old_shape = {"schema": 1, "image": IMAGE, "image_config_id": resolved_id, "architecture": "arm64", "os": "linux",
        "network": "none", "memory_mb": 192, "cpus": 0.5, "pids": 32, "disk_mb": 16,
        "rpc": digest(verification.RPC_SOURCE)}
    expected = {**old_shape, "controller": hashlib.sha256(Path(verification.__file__).read_bytes()).hexdigest(),
        "execution": hashlib.sha256(Path(DockerSandbox.__module__.replace(".", "/") + ".py").read_bytes()).hexdigest()}
    assert verifier.environment_digest == digest(expected)
    c = case(tmp_path)
    engine = ReferenceEngine(c.store, c.artifacts, tmp_path / "runs", sandbox_image=IMAGE)
    task = engine.submit_fixture(list_tasks(split="calibration")[0].task_id,
        tenant="environment-tenant", key="old-source-contract")
    # Historical tasks preserve their original environment bytes; new startup cannot reinterpret them.
    with c.store._tx() as (connection, guard):
        saved = c.store._task(connection, task["tenant_id"], task["task_id"])
        saved["contract"]["environment_digest"] = digest(old_shape)
        c.store._save(connection, "tasks", saved["task_id"], saved["tenant_id"], saved["task_id"], saved)
    before = c.store.snapshot(task["tenant_id"], task["task_id"])
    with pytest.raises(ValueError, match="environment drift"):
        engine.run_task(task["tenant_id"], task["task_id"])
    assert c.store.snapshot(task["tenant_id"], task["task_id"]) == before


@pytest.mark.docker
@pytest.mark.parametrize("control", ["correct", "baseline", "stdout_forgery"])
def test_E09_actual_linux_verifier_uses_journal_and_external_assertions(tmp_path, control):
    from service.verification import LinuxVerifier
    from workloads import list_tasks
    from workloads.registry import ROOT, TARGET_FILES
    image = cached_image()
    selected = list_tasks(split="calibration")[0]
    directory = ROOT / "oracle" / "reference" if control != "baseline" else selected.baseline_path
    files = {name: (directory / name).read_text() for name in TARGET_FILES}
    if control == "stdout_forgery":
        files["issue_tracker.py"] = "print('{\"ok\":true,\"value\":null}')\n" + files["issue_tracker.py"]
    verifier = LinuxVerifier(image)
    c = case(tmp_path, grader=selected.as_dict()["grader_sha256"], environment=verifier.environment_digest, files=files)
    real_lifecycle(c)
    try:
        result = verifier.verify(files, selected, sandbox_id=c.reservation["sandbox_id"], lifecycle=c.lifecycle)
        assert result["mode"] == "linux_candidate_rpc_external_grader"
        assert result["passed"] is (control == "correct")
        assert result["retirement"]["retired"] is True
        saved = journal(c)
        assert len(saved["instances"]) == 1 and saved["instances"][0]["state"] == "retired"
        assert saved["source"]["input_digest"] == digest(files)
        assert saved["source"]["tree_digest"] == tree_digest(files)
        assert saved["phase"] == "open"
        assert reconcile(c)["status"] == "retired"
        assert snapshot(c)["verifications"] == []
    finally:
        reconcile(c)
        c.store.close()


@pytest.mark.docker
@pytest.mark.parametrize("control", ["correct", "wrong", "stdout_forgery"])
def test_E09_actual_function_verifier_multiple_private_cases_and_exact_bridge_input(tmp_path, control):
    from service.repair_verification import BRIDGE_PATH, BRIDGE_SOURCE, PythonFunctionRecipe, PythonFunctionVerifier
    image = cached_image()
    private = "PRIVATE_NEVER_JOURNAL_88112233"
    recipe = PythonFunctionRecipe.from_dict({"schema": "python-function-recipe-v1", "recipe_id": "independent-add-v1",
        "source_paths": ["calc.py"], "module_path": "calc.py", "functions": ["add"],
        "worker_cases": [{"id": "public-one", "function": "add", "args": [1, 2], "kwargs": {}, "expect": {"value": 3}}],
        "final_cases": [
            {"id": private + "a", "function": "add", "args": [11, 31], "kwargs": {}, "expect": {"value": 42}},
            {"id": private + "b", "function": "add", "args": [-7, 2], "kwargs": {}, "expect": {"value": -5}},
            {"id": private + "c", "function": "add", "args": [0, 0], "kwargs": {}, "expect": {"value": 0}}]})
    files = dict(FILES)
    if control == "wrong":
        files["calc.py"] = "def add(a, b): return a - b\n"
    if control == "stdout_forgery":
        files["calc.py"] = "print('{\"schema\":1,\"ok\":true,\"value\":42}')\n" + files["calc.py"]
    verifier = PythonFunctionVerifier(image)
    c = case(tmp_path, grader=recipe.grader_digest, environment=verifier.environment_for(recipe), files=files)
    real_lifecycle(c)
    try:
        result = verifier.verify(files, recipe, purpose="final", sandbox_id=c.reservation["sandbox_id"], lifecycle=c.lifecycle)
        assert result["mode"] == "linux_stateless_function_rpc"
        assert result["passed"] is (control == "correct")
        assert result["retirement"]["retired"] is True
        saved = journal(c)
        assert saved["source"]["purpose"] == "final"
        assert saved["source"]["input_digest"] == digest({**files, BRIDGE_PATH: BRIDGE_SOURCE})
        assert saved["source"]["tree_digest"] == tree_digest(files)
        assert saved["max_instances"] == 3
        assert all(row["state"] == "retired" for row in saved["instances"])
        assert len(saved["instances"]) == (1 if control == "stdout_forgery" else 3)
        assert len({row["container_id"] for row in saved["instances"]}) == len(saved["instances"])
        assert private not in canonical({"journal": saved, "result": result, "snapshot": snapshot(c)}).decode()
        assert reconcile(c)["status"] == "retired"
        assert snapshot(c)["verifications"] == []
    finally:
        reconcile(c)
        c.store.close()


@pytest.mark.docker
def test_E04_actual_repair_aggregate_publication_failure_preserves_cleanup_journal(tmp_path, monkeypatch):
    from service.environment_recovery import EnvironmentLifecycle, reconcile_environment
    from service.repair import RepairEngine
    from service.repair_verification import PythonFunctionRecipe, PythonFunctionVerifier
    image = cached_image()
    item = {"id": "public-one", "function": "add", "args": [1, 2], "kwargs": {}, "expect": {"value": 3}}
    recipe = PythonFunctionRecipe.from_dict({"schema": "python-function-recipe-v1", "recipe_id": "publication-add-v1",
        "source_paths": ["calc.py"], "module_path": "calc.py", "functions": ["add"],
        "worker_cases": [item], "final_cases": [{**item, "id": "private-one"}]})
    verifier = PythonFunctionVerifier(image)
    c = case(tmp_path, grader=recipe.grader_digest, environment=verifier.environment_for(recipe))
    real_lifecycle(c)
    c.store.retire_sandbox(c.task["tenant_id"], c.reservation["sandbox_id"],
        {"kind": "independent-no-process-fixture-retirement", "retired": True})
    engine = RepairEngine(c.store, c.artifacts, tmp_path / "runs", verifier, environment_backend=c.backend)
    original = c.artifacts.put_json
    def fail_report(tenant, task_id, value):
        if value.get("mode") == "linux_stateless_function_rpc":
            raise RuntimeError("independent aggregate publication lost")
        return original(tenant, task_id, value)
    monkeypatch.setattr(c.artifacts, "put_json", fail_report)
    with pytest.raises(RuntimeError, match="publication lost"):
        engine._checks(c.task["tenant_id"], c.task["task_id"], FILES, recipe, "worker")
    snapshot_after = snapshot(c)
    rows = [row for row in snapshot_after["sandboxes"] if row.get("environment_journal")]
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "reserved" and row["environment_journal"]["phase"] == "open"
    assert row["environment_journal"]["instances"][0]["state"] == "retired"
    assert snapshot_after["verifications"] == []
    monkeypatch.setattr(c.artifacts, "put_json", original)
    lifecycle = EnvironmentLifecycle(c.store, c.artifacts, c.task["tenant_id"], c.task["task_id"], row["sandbox_id"], c.backend)
    assert reconcile_environment(lifecycle, c.backend)["status"] == "retired"
    assert snapshot(c)["verifications"] == []
    c.store.close()


def _actual_lost_create_child(input_path):
    from service.environment_recovery import DockerEnvironmentBackend, EnvironmentLifecycle, launch_value
    data = json.loads(Path(input_path).read_text())
    path = Path(data["path"])
    artifacts = LocalArtifacts(path / "artifacts")
    store = RuntimeStore(data["url"], artifacts)
    def kill_after_create(argv, **options):
        result = bounded_process(argv, **options)
        if argv[:2] == ["docker", "create"]:
            (path / "actual-create-observation.json").write_bytes(canonical({
                "argv": argv, "producer_pid": os.getpid(), "exit_code": result["exit_code"], "output": result["output"].decode(),
                "reason": result["reason"], "truncated": result["truncated"],
                "process_group_retired": result["process_group_retired"]}))
            os._exit(91)
        return result
    backend = DockerEnvironmentBackend("real-local-test", runner=kill_after_create)
    lifecycle = EnvironmentLifecycle(store, artifacts, data["tenant"], data["task_id"], data["sandbox_id"], backend)
    launch = launch_value(data["image"], memory_mb=192, cpus=0.5, pids=32, disk_mb=16, timeout=20)
    binding = lifecycle.instance(ordinal=0, source=data["source"], launch=launch, max_instances=1)
    DockerSandbox(data["image"], journal_binding=binding).start(FILES)
    raise AssertionError("Child must terminate at exact create ACK boundary")


def _actual_reconcile_child(input_path):
    from service.environment_recovery import DockerEnvironmentBackend, EnvironmentLifecycle, reconcile_environment
    data = json.loads(Path(input_path).read_text())
    path = Path(data["path"])
    artifacts = LocalArtifacts(path / "artifacts")
    store = RuntimeStore(data["url"], artifacts)
    backend = DockerEnvironmentBackend("real-local-test")
    lifecycle = EnvironmentLifecycle(store, artifacts, data["tenant"], data["task_id"], data["sandbox_id"], backend)
    before = store.read_environment_journal(data["tenant"], data["sandbox_id"])
    result = reconcile_environment(lifecycle, backend)
    after = store.snapshot(data["tenant"], data["task_id"])
    repeated = reconcile_environment(lifecycle, backend)
    assert store.snapshot(data["tenant"], data["task_id"]) == after
    (path / "actual-reconciliation.json").write_bytes(canonical({"before": before, "result": result,
        "after": after, "repeat": repeated, "controller_pid": os.getpid()}))
    store.close()


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def actual_database(request):
    if request.param == "sqlite":
        yield None
        return
    if not os.environ.get("CAM_TEST_POSTGRES_URL"):
        pytest.skip("CAM_TEST_POSTGRES_URL not configured")
    admin = sa.create_engine(os.environ["CAM_TEST_POSTGRES_URL"])
    namespace = "environment_actual_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    url = sa.engine.make_url(os.environ["CAM_TEST_POSTGRES_URL"]).update_query_dict({"options": "-csearch_path=" + namespace})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


@pytest.mark.docker
def test_E02_actual_create_ack_loss_reconciles_from_separate_interpreter(tmp_path, actual_database):
    from service.environment_recovery import DockerEnvironmentBackend, EnvironmentLifecycle, reconcile_environment
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit cached Docker image required")
    c = case(tmp_path, url=actual_database)
    data = {"path": str(tmp_path), "url": c.store.engine.url.render_as_string(hide_password=False),
        "tenant": c.task["tenant_id"], "task_id": c.task["task_id"], "sandbox_id": c.reservation["sandbox_id"],
        "source": c.source, "image": image}
    input_path = tmp_path / "child-input.json"
    input_path.write_bytes(canonical(data))
    c.store.close()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent) + os.pathsep + str(Path(__file__).resolve().parents[1])
    child = subprocess.run([sys.executable, "-c",
        "from test_environment_recovery import _actual_lost_create_child; import sys; _actual_lost_create_child(sys.argv[1])",
        str(input_path)], env=env, capture_output=True, text=True, timeout=60)
    assert child.returncode == 91, child.stdout + child.stderr
    store = RuntimeStore(data["url"], LocalArtifacts(tmp_path / "artifacts"))
    backend = DockerEnvironmentBackend("real-local-test")
    lifecycle = EnvironmentLifecycle(store, store.artifact_store, data["tenant"], data["task_id"], data["sandbox_id"], backend)
    saved = store.read_environment_journal(data["tenant"], data["sandbox_id"])["environment_journal"]
    row = saved["instances"][0]
    assert row["state"] == "create_intent" and row["container_id"] is None
    created = json.loads((tmp_path / "actual-create-observation.json").read_text())
    assert created["exit_code"] == 0 and created["reason"] == "exited" and not created["truncated"]
    cid = created["output"].strip()
    try:
        store.close()
        controller = subprocess.run([sys.executable, "-c",
            "from test_environment_recovery import _actual_reconcile_child; import sys; _actual_reconcile_child(sys.argv[1])",
            str(input_path)], env=env, capture_output=True, text=True, timeout=60)
        assert controller.returncode == 0, controller.stdout + controller.stderr
        measured = json.loads((tmp_path / "actual-reconciliation.json").read_text())
        assert len({measured["controller_pid"], created["producer_pid"], os.getpid()}) == 3
        result = measured["result"]
        assert result["status"] == "retired"
        store = RuntimeStore(data["url"], LocalArtifacts(tmp_path / "artifacts"))
        lifecycle = EnvironmentLifecycle(store, store.artifact_store, data["tenant"], data["task_id"], data["sandbox_id"], backend)
        final = store.read_environment_journal(data["tenant"], data["sandbox_id"])["environment_journal"]
        assert final["instances"][0]["container_id"] == cid
        assert final["instances"][0]["creation_nonce"] == row["creation_nonce"]
        assert final["instances"][0]["state"] == "retired"
        before = store.snapshot(data["tenant"], data["task_id"])
        assert reconcile_environment(lifecycle, backend)["status"] == "retired"
        assert store.snapshot(data["tenant"], data["task_id"]) == before
        if os.environ.get("CAM_ENVIRONMENT_EVIDENCE_DIR"):
            evidence = Path(os.environ["CAM_ENVIRONMENT_EVIDENCE_DIR"])
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / ("actual-acklost-" + c.reservation["sandbox_id"] + ".json")).write_bytes(canonical({
                "create": created, "reconciliation": measured, "backend": backend.backend, "image": image}))
    finally:
        # Cleanup only the exact ID observed from this child, even on assertion failure.
        if len(cid) == 64 and all(x in "0123456789abcdef" for x in cid):
            bounded_process(["docker", "rm", "--force", cid], timeout=30)
        store.close()
