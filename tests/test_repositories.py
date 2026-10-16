import dataclasses
import os
import subprocess

import pytest

from service.artifacts import digest_json
from service.execution import tree_digest
from service.repositories import FrozenRepository, freeze_repository


def test_snapshot_is_detached_immutable_and_round_trips():
    files = {"app.py": "print('source')\n", "README.md": "public documentation"}
    allowed = ["app.py"]
    frozen = FrozenRepository.from_files("owned-repo", files, allowed)
    files["app.py"] = "mutated"
    allowed.clear()
    assert frozen.files["app.py"] == "print('source')\n"
    assert frozen.allowed_paths == ("app.py",)
    assert frozen.base_git_commit is None
    assert frozen.tree_digest == tree_digest(dict(frozen.files))
    with pytest.raises(TypeError):
        frozen.files["app.py"] = "mutated"
    with pytest.raises(dataclasses.FrozenInstanceError):
        frozen.repo_id = "new"
    exported = frozen.as_dict()
    assert FrozenRepository.from_dict(exported) == frozen
    exported["files"]["app.py"] = "mutated"
    exported["allowed_paths"].clear()
    assert frozen.files["app.py"] == "print('source')\n"
    assert frozen.allowed_paths == ("app.py",)


def test_intake_selects_explicit_paths_and_preserves_bytes(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_bytes(b"# Never imported\r\nraise RuntimeError('must not run')\r\n")
    (tmp_path / ".env").write_text("excluded")
    (tmp_path / "oracle").mkdir()
    (tmp_path / "oracle" / "answer.py").write_text("excluded")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("ordinary intake must not use Git"))
    frozen = freeze_repository(tmp_path, "repo", ["app.py"], ["app.py"])
    (tmp_path / "app.py").write_text("changed after intake")
    assert dict(frozen.files) == {"app.py": "# Never imported\r\nraise RuntimeError('must not run')\r\n"}


@pytest.mark.parametrize("path", [
    "../a.py", "/a.py", "a//b.py", "./a.py", "a/./b.py", "a/../b.py", "a\\b.py", "a.py/",
    ".env", ".git/config.py", "app/.hidden.py", "app.py\x00", "app.py\n", "a:b.py", "café.py",
    "oracle/answer.py", "references/source.py", "reference.py", "private/cases.json", "private_cases.json",
    "secrets.json", "credentials.toml", "mySecretConfig.json", "api_key.json", "aws/key.txt", "id_rsa.txt", "_cam_bridge.py",
    "bridge/runner.py", "app.sh", "app.PY", "x" * 129 + ".py",
])
def test_protected_and_alias_paths_are_rejected(path):
    with pytest.raises(ValueError):
        FrozenRepository.from_files("repo", {path: "text"}, [path])


def test_writable_paths_are_an_explicit_subset():
    files = {"app.py": "source", "tests/public.py": "public"}
    assert FrozenRepository.from_files("repo", files, []).allowed_paths == ()
    with pytest.raises(ValueError, match="subset"):
        FrozenRepository.from_files("repo", files, ["absent.py"])
    with pytest.raises(ValueError, match="duplicate"):
        FrozenRepository.from_files("repo", files, ["app.py", "app.py"])
    with pytest.raises(ValueError):
        FrozenRepository.from_files("repo", files, "app.py")
    with pytest.raises(ValueError, match="collision"):
        FrozenRepository.from_files("repo", {"a.py": "text", "a.py/b.py": "text"}, [])


@pytest.mark.parametrize("files", [{"app.py": "a", "APP.py": "b"}, {"SRC/a.py": "a", "src/b.py": "b"}])
def test_case_aliases_are_rejected(files):
    with pytest.raises(ValueError, match="alias"):
        FrozenRepository.from_files("repo", files, [])


def test_intake_rejects_missing_duplicate_or_undeclared_paths(tmp_path):
    (tmp_path / "app.py").write_text("source")
    for paths, allowed in [([], []), (["app.py", "app.py"], []), (["app.py"], ["other.py"]), (["absent.py"], [])]:
        with pytest.raises(ValueError):
            freeze_repository(tmp_path, "repo", paths, allowed)


@pytest.mark.parametrize("kind", ["root", "ancestor", "directory", "leaf"])
def test_symlink_at_any_component_rejected(tmp_path, kind):
    real = tmp_path / "real"
    real.mkdir()
    (real / "app.py").write_text("source")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    if kind == "root":
        root, source = link, "app.py"
    elif kind == "ancestor":
        (real / "nested").mkdir()
        (real / "nested" / "app.py").write_text("source")
        root, source = link / "nested", "app.py"
    elif kind == "directory":
        (real / "dir").symlink_to(real, target_is_directory=True)
        root, source = real, "dir/app.py"
    else:
        (real / "link.py").symlink_to(real / "app.py")
        root, source = real, "link.py"
    with pytest.raises(ValueError):
        freeze_repository(root, "repo", [source], [])


def test_nonregular_source_rejected_without_blocking(tmp_path):
    os.mkfifo(tmp_path / "pipe.py")
    with pytest.raises(ValueError, match="regular"):
        freeze_repository(tmp_path, "repo", ["pipe.py"], [])


@pytest.mark.parametrize("data", [b"\xff\xfe", b"a\x00b", b"a\x01b"])
def test_binary_and_invalid_utf8_rejected(tmp_path, data):
    (tmp_path / "app.py").write_bytes(data)
    with pytest.raises(ValueError, match="UTF-8"):
        freeze_repository(tmp_path, "repo", ["app.py"], [])


def test_byte_limits_count_utf8_and_accept_exact_boundary(tmp_path):
    text = "é" * (64 * 1024)
    exact = {"a.py": text, "b.py": text}
    assert len(FrozenRepository.from_files("repo", exact, []).files) == 2
    with pytest.raises(ValueError, match="byte limit"):
        FrozenRepository.from_files("repo", {"a.py": text + "é"}, [])
    with pytest.raises(ValueError, match="byte limit"):
        FrozenRepository.from_files("repo", {**exact, "c.py": "x"}, [])
    (tmp_path / "app.py").write_bytes(b"x" * (128 * 1024 + 1))
    with pytest.raises(ValueError, match="byte limit"):
        freeze_repository(tmp_path, "repo", ["app.py"], [])
    for name, content in {**exact, "c.py": "x"}.items():
        (tmp_path / name).write_text(content)
    with pytest.raises(ValueError, match="total byte limit"):
        freeze_repository(tmp_path, "repo", list(exact) + ["c.py"], [])


def test_file_count_and_invalid_text_limits():
    exact = {f"f{i}.py": "" for i in range(50)}
    assert len(FrozenRepository.from_files("repo", exact, []).files) == 50
    with pytest.raises(ValueError, match="bounded"):
        FrozenRepository.from_files("repo", {**exact, "extra.py": ""}, [])
    for files in [{}, {"a.py": 3}, {"a.py": "\ud800"}]:
        with pytest.raises(ValueError):
            FrozenRepository.from_files("repo", files, [])


@pytest.mark.parametrize("field,value", [
    ("tree_digest", "0" * 64), ("manifest_digest", "0" * 64), ("schema", True), ("schema", 2),
    ("base_git_commit", "HEAD"), ("repo_id", "../repo"), ("files", {"a.py": "altered"}),
    ("allowed_paths", ["other.py"]),
])
def test_serialized_manifest_validation(field, value):
    manifest = FrozenRepository.from_files("repo", {"a.py": "source"}, ["a.py"]).as_dict()
    manifest[field] = value
    with pytest.raises(ValueError):
        FrozenRepository.from_dict(manifest)


def test_unknown_manifest_fields_and_rehashed_bad_capability_rejected():
    manifest = FrozenRepository.from_files("repo", {"a.py": "source"}, []).as_dict()
    with pytest.raises(ValueError, match="fields"):
        FrozenRepository.from_dict({**manifest, "extra": True})
    manifest["allowed_paths"] = ["a.py", "a.py"]
    manifest["manifest_digest"] = digest_json({k: v for k, v in manifest.items() if k != "manifest_digest"})
    with pytest.raises(ValueError, match="duplicate"):
        FrozenRepository.from_dict(manifest)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True).stdout.decode().strip()


@pytest.fixture
def git_repository(tmp_path):
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "user.email", "fixture@example.test")
    git(tmp_path, "config", "user.name", "Fixture")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("source\n")
    (tmp_path / "README.md").write_text("documentation\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "fixture")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


def test_optional_git_provenance_exact_selected_bytes(git_repository):
    root, commit = git_repository
    # Unselected dirt is not a claim of cleanliness for the whole repository.
    (root / "README.md").write_text("unselected changed")
    frozen = freeze_repository(root, "repo", ["src/app.py"], ["src/app.py"], commit)
    assert frozen.base_git_commit == commit
    assert frozen.tree_digest != commit
    assert FrozenRepository.from_dict(frozen.as_dict()).base_git_commit == commit
    assert freeze_repository(root, "repo", ["src/app.py"], []).base_git_commit is None


@pytest.mark.parametrize("kind", ["head", "working", "staged", "untracked", "mode", "working_mode"])
def test_git_provenance_rejects_changed_selected_state(git_repository, kind):
    root, commit = git_repository
    paths = ["src/app.py"]
    if kind == "head":
        commit = "0" * 40
    elif kind == "working":
        (root / "src" / "app.py").write_text("dirty")
    elif kind == "staged":
        (root / "src" / "app.py").write_text("staged")
        git(root, "add", "src/app.py")
        (root / "src" / "app.py").write_text("source\n")
    elif kind == "untracked":
        (root / "new.py").write_text("untracked")
        paths = ["new.py"]
    elif kind == "mode":
        git(root, "update-index", "--chmod=+x", "src/app.py")
    else:
        (root / "src" / "app.py").chmod(0o755)
    with pytest.raises(ValueError, match="Git"):
        freeze_repository(root, "repo", paths, [], commit)


def test_git_provenance_rejects_gitfiles_and_metadata_symlinks(git_repository, tmp_path):
    root, commit = git_repository
    (root / ".git" / "redirect").symlink_to(root / "src")
    with pytest.raises(ValueError, match="Git"):
        freeze_repository(root, "repo", ["src/app.py"], [], commit)
    (root / ".git" / "redirect").unlink()
    (root / ".git").rename(root / "metadata")
    (root / ".git").write_text("gitdir: metadata\n")
    with pytest.raises(ValueError, match="Git"):
        freeze_repository(root, "repo", ["src/app.py"], [], commit)


def test_git_does_not_execute_fsmonitor_or_hooks(git_repository):
    root, commit = git_repository
    marker = root / "hook-ran"
    hook = root / ".git" / "hooks" / "danger"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    hook.chmod(0o700)
    git(root, "config", "core.fsmonitor", str(hook))
    git(root, "config", "core.hooksPath", str(hook.parent))
    assert freeze_repository(root, "repo", ["src/app.py"], [], commit).base_git_commit == commit
    assert not marker.exists()
