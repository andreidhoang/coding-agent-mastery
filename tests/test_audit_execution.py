"""Disposable regressions discovered by the 2026-10-09 trust-boundary review."""

import os
import signal
import sys
import uuid

import pytest

from service.execution import DockerSandbox, bounded_process, tree_digest
from service.verification import LinuxVerifier
from workloads import list_tasks
from workloads.registry import ROOT, TARGET_FILES


def _image():
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit locally present sandbox image required")
    return image


@pytest.mark.docker
def test_duplicate_container_creation_must_not_delete_live_container():
    image = _image()
    identity = "review" + uuid.uuid4().hex
    first = DockerSandbox(image, identity=identity)
    second = DockerSandbox(image, identity=identity)
    try:
        first.start({"hello.py": "print('first')\n"})
        with pytest.raises(RuntimeError):
            second.start({"hello.py": "print('second')\n"})
        observed = first.run(["python", "hello.py"])
        assert observed["exit_code"] == 0, observed
        assert observed["output"].strip() == "first"
    finally:
        # Each cleanup is confined to this test's UUID-named container.
        try:
            first.close()
        except RuntimeError:
            pass


@pytest.mark.docker
def test_malformed_rpc_is_not_an_expected_application_value_error():
    files = {p: (ROOT / "oracle/reference" / p).read_text() for p in TARGET_FILES}
    files["issue_tracker.py"] = files["issue_tracker.py"].replace(
        'raise ValueError("CSV headers must be issue_id,title")',
        "import os; print('malformed response', flush=True); os._exit(0)",
    )
    task = next(t for t in list_tasks(split="calibration") if "tenant_idempotency" in t.requirements)
    result = LinuxVerifier(_image()).verify(files, task)
    assert not result["passed"], result


def test_verified_digest_identifies_bytes_copied_before_caller_mutation(monkeypatch):
    files = {"issue_tracker.py": "original", "client.py": "original"}
    verified_digest = tree_digest(files)

    class Sandbox:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, copied):
            assert tree_digest(copied) == verified_digest
            # Model a caller retaining and concurrently changing its input object.
            files["issue_tracker.py"] = "different unverified bytes"

        def close(self):
            return {"retired": True}

    class Grader:
        def grade(self, *args):
            return {"passed": True, "criteria": []}

    import service.verification as verification

    monkeypatch.setattr(verification, "DockerSandbox", Sandbox)
    monkeypatch.setattr(verification, "_grader", lambda: Grader())
    verifier = object.__new__(LinuxVerifier)
    verifier.image = "sha256:" + "0" * 64
    verifier.environment_digest = "e" * 64
    receipt = verifier.verify(files, list_tasks(split="calibration")[0])
    assert receipt["tree_digest"] == verified_digest


def test_bounded_launcher_does_not_leave_background_child(tmp_path):
    pidfile = tmp_path / "trusted-child.pid"
    # This is a fixed review-owned process fixture, never candidate code.
    source = (
        "import subprocess,sys,pathlib; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(pidfile)!r}).write_text(str(child.pid))"
    )
    pid = None
    try:
        result = bounded_process([sys.executable, "-c", source], timeout=1)
        pid = int(pidfile.read_text())
        assert result["reason"] == "exited"
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("failure", ["missing_value", "malformed_json", "terminated", "runtime_transport"])
def test_transport_schema_failure_latches_even_if_grader_catches_every_exception(monkeypatch, failure):
    import service.verification as verification

    class Sandbox:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, files):
            pass

        def run(self, *args, **kwargs):
            if failure == "runtime_transport":
                raise RuntimeError("transport failed")
            return {
                "exit_code": 1 if failure == "terminated" else 0,
                "reason": "exited",
                "duration_seconds": 0,
                "output": "malformed" if failure == "malformed_json" else '{"ok":true}',
            }

        def close(self):
            return {"retired": True}

    class Grader:
        def grade(self, requirements, tracker_module, client_module, variant):
            try:
                tracker_module.IssueTracker()
            except Exception:
                pass  # Even this must not erase the independent boundary failure.
            return {"passed": True, "criteria": [{"passed": True}]}

    monkeypatch.setattr(verification, "DockerSandbox", Sandbox)
    monkeypatch.setattr(verification, "_grader", lambda: Grader())
    verifier = object.__new__(LinuxVerifier)
    verifier.image = "sha256:" + "0" * 64
    verifier.environment_digest = "e" * 64
    result = verifier.verify({"issue_tracker.py": "a", "client.py": "b"}, list_tasks(split="calibration")[0])
    assert result["passed"] is False
    assert result["cause"] == "candidate_rpc_boundary_failed"
    assert result["boundary_failures"]


def test_fixture_verified_digest_is_copied_before_grader_mutates_caller(monkeypatch):
    import service.verification as verification

    files = {p: (ROOT / "oracle/reference" / p).read_text() for p in TARGET_FILES}
    expected = tree_digest(files)

    class Grader:
        def grade(self, *args):
            files["client.py"] = "unverified new content"
            return {"passed": True, "criteria": []}

    monkeypatch.setattr(verification, "_grader", lambda: Grader())
    result = verification.FixtureVerifier().verify(files, list_tasks(split="calibration")[0])
    assert result["passed"] and result["tree_digest"] == expected
    assert tree_digest(files) != expected


def test_bounded_launcher_escalates_for_child_ignoring_term_after_leader_exit(tmp_path):
    ready = tmp_path / "ready"
    pidfile = tmp_path / "pid"
    child = (
        "import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); time.sleep(30)"
    )
    source = (
        "import subprocess,sys,pathlib,time; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdin=subprocess.DEVNULL,"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(pidfile)!r}).write_text(str(p.pid)); "
        f"ready=pathlib.Path({str(ready)!r}); "
        "exec('while not ready.exists(): time.sleep(.005)')"
    )
    pid = None
    try:
        result = bounded_process([sys.executable, "-c", source], timeout=1)
        pid = int(pidfile.read_text())
        assert result["reason"] == "exited"
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.docker
def test_rejected_same_name_instance_close_has_no_cleanup_authority():
    first = DockerSandbox(_image(), identity="review" + uuid.uuid4().hex)
    second = DockerSandbox(_image(), identity=first.name.removeprefix("cam-sandbox-"))
    try:
        first.start({"hello.py": "print('owned first')"})
        with pytest.raises(RuntimeError):
            second.start({"hello.py": "print('rejected second')"})
        assert second.container_id is None
        assert second.close()["retired"]
        assert first.run(["python", "hello.py"])["output"].strip() == "owned first"
        assert first.container_id and first.creation_nonce != second.creation_nonce
    finally:
        first.close()


def test_ambiguous_create_cannot_remove_a_different_nonce_container(monkeypatch):
    calls = []
    sandbox = DockerSandbox("sha256:" + "a" * 64)
    wrong_id = "b" * 64

    def launcher(argv, **kwargs):
        import json

        calls.append(argv)
        if "create" in argv:
            return {"exit_code": -9, "reason": "timeout", "output": b""}
        if "ps" in argv:
            return {"exit_code": 0, "reason": "exited", "output": wrong_id.encode()}
        if "inspect" in argv:
            raw = {
                "Id": wrong_id,
                "Name": "/" + sandbox.name,
                "Config": {"Labels": {"coding-agent-mastery-create-nonce": "different-instance"}},
            }
            return {"exit_code": 0, "reason": "exited", "output": json.dumps(raw).encode()}
        raise AssertionError("unowned instance must never reach removal")

    monkeypatch.setattr("service.execution.bounded_process", launcher)
    with pytest.raises(RuntimeError, match="unknown"):
        sandbox.start({"a.py": "text"})
    assert sandbox.container_id is None and sandbox.provisioning_attempted
    assert not any("rm" in argv for argv in calls)


@pytest.mark.docker
def test_cleanup_owned_id_survives_container_name_rebinding():
    original_identity = "review" + uuid.uuid4().hex
    first = DockerSandbox(_image(), identity=original_identity)
    second = DockerSandbox(_image(), identity=original_identity)
    try:
        first.start({"hello.py": "print('old instance')"})
        renamed = "cam-sandbox-review" + uuid.uuid4().hex
        result = bounded_process(["docker", "rename", first.container_id, renamed])
        assert result["exit_code"] == 0
        second.start({"hello.py": "print('new instance')"})
        assert first.container_id != second.container_id
        assert first.close()["retired"]
        assert second.run(["python", "hello.py"])["output"].strip() == "new instance"
    finally:
        second.close()
        first.close()
