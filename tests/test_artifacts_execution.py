import os
import sys

import pytest

from service.artifacts import LocalArtifacts, digest_bytes
from service.execution import DockerSandbox, Workspace, bounded_process, materialize
from service.integration import candidate_manifest, integrate_candidates


def test_artifact_integrity_scope_and_immutable_upload(tmp_path):
    store = LocalArtifacts(tmp_path)
    ref = store.put("tenant-a", "task", b"original")
    assert store.put("tenant-a", "task", b"original") == ref
    with pytest.raises(FileNotFoundError):
        store.get("tenant-b", "task", ref["digest"])
    (tmp_path / "tenant-a" / "task" / ref["digest"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        store.get("tenant-a", "task", ref["digest"])
    with pytest.raises(ValueError):
        store.put("../escape", "task", b"a")


def test_guarded_edit_and_symlink_denial(tmp_path):
    materialize(tmp_path / "work", {"app.py": "return a - b\n", "tests.py": "protected\n"})
    work = Workspace(tmp_path / "work", ["app.py"])
    read = work.read("app.py")
    work.replace("app.py", read["digest"], "a - b", "a + b")
    with pytest.raises(ValueError, match="stale"):
        work.replace("app.py", read["digest"], "a + b", "a - b")
    with pytest.raises(PermissionError):
        work.replace("tests.py", digest_bytes(b"protected\n"), "protected", "pass")
    (tmp_path / "outside").write_text("secret")
    (tmp_path / "work" / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(PermissionError):
        work.read("link")
    with pytest.raises(ValueError):
        work.read("../outside")


def test_integrator_rejects_conflicts_wrong_base_and_unlisted_changes():
    base = {"a.py": "old\n", "b.py": "old\n"}
    a = candidate_manifest(base, {**base, "a.py": "new\n"}, ["a.py"], {}, ["R1"])
    b = candidate_manifest(base, {**base, "b.py": "new\n"}, ["b.py"], {}, ["R2"])
    assert integrate_candidates(base, [a, b]) == {"a.py": "new\n", "b.py": "new\n"}
    conflict = candidate_manifest(base, {**base, "a.py": "different\n"}, ["a.py"], {}, ["R1"])
    with pytest.raises(ValueError, match="conflict"):
        integrate_candidates(base, [a, conflict])
    with pytest.raises(ValueError):
        integrate_candidates({"a.py": "other"}, [a])
    a["files"]["b.py"] = "unlisted"
    with pytest.raises(ValueError, match="integrity"):
        integrate_candidates(base, [a])


def test_bounded_launcher_timeout_and_output():
    result = bounded_process([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05)
    assert result["reason"] == "timeout"
    result = bounded_process([sys.executable, "-c", "print('x'*100000)"], max_output=200)
    assert result["reason"] == "output_limit" and len(result["output"]) == 200


@pytest.mark.docker
def test_linux_backend_enforces_boundary_and_retirement():
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if not image:
        pytest.skip("set CAM_TEST_SANDBOX_IMAGE to explicit locally pinned Python image")
    sandbox = DockerSandbox(image)
    try:
        sandbox.start({"hello.py": "print('fixture')\n"})
        result = sandbox.run(["python", "hello.py"])
        assert result["exit_code"] == 0 and result["output"].strip() == "fixture"
        probe = sandbox.run(
            [
                "python",
                "-I",
                "-c",
                "import os,socket,json; print(json.dumps({'uid':os.getuid(),'env':sorted(os.environ),'home':os.path.exists('/Users'),'socket':os.path.exists('/var/run/docker.sock')}))",
            ]
        )
        import json

        data = json.loads(probe["output"])
        assert data["uid"] == 65534 and not data["home"] and not data["socket"]
        assert not any("KEY" in key or "TOKEN" in key or "DATABASE" in key for key in data["env"])
        assert sandbox.run(["python", "-c", "open('/etc/forbidden','w').write('x')"])["exit_code"] != 0
        assert (
            sandbox.run(["python", "-c", "import socket; socket.create_connection(('1.1.1.1',443),1)"])[
                "exit_code"
            ]
            != 0
        )
    finally:
        retirement = sandbox.close()
    assert retirement["retired"]
