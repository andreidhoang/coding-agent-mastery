"""Explicit, bounded text intake; candidate source is never imported on the host.

This is a trusted control-plane snapshot boundary, not hostile filesystem isolation.
Git provenance is optional and certifies selected files only, not the entire checkout.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from .artifacts import digest_json
from .contracts import identity
from .execution import tree_digest

MAX_FILES = 50
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 256 * 1024
_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml"}
_PROTECTED = {
    "oracle", "oracles", "reference", "references", "private", "secret", "secrets",
    "credential", "credentials", "password", "passwords", "token", "tokens", "ssh", "aws",
    "bridge", "keys", "apikey", "apikeys",
}
_FIELDS = {
    "schema", "repo_id", "files", "allowed_paths", "base_git_commit", "tree_digest", "manifest_digest",
}


def _source_path(value: str) -> str:
    if (
        not isinstance(value, str) or len(value) > 512
        or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.\-/]*", value)
    ):
        raise ValueError("invalid canonical source path")
    parts = value.split("/")
    for part in parts:
        tokens = set(re.split(r"[_.-]+", part.lower()))
        if (
            not part or part.startswith(".") or len(part) > 128
            or tokens & _PROTECTED or part.lower().startswith("_cam_bridge")
            or any(word in part.lower() for word in ("oracle", "reference", "credential", "secret", "password"))
            or "api_key" in part.lower() or part.lower().startswith(("id_rsa", "id_ed25519"))
        ):
            raise ValueError("protected or noncanonical source path")
    if Path(value).suffix not in _SUFFIXES:
        raise ValueError("unsupported source suffix")
    return value


def _paths(values: Sequence[str], name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > MAX_FILES or (nonempty and not values):
        raise ValueError(f"{name} must be a bounded explicit path list")
    result = tuple(_source_path(value) for value in values)
    if len(set(result)) != len(result):
        raise ValueError(f"duplicate {name}")
    return tuple(sorted(result))


def _commit(value: str | None) -> str | None:
    if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value)):
        raise ValueError("base Git commit must be full lowercase object identity")
    return value


@dataclass(frozen=True, slots=True)
class FrozenRepository:
    repo_id: str
    files: Mapping[str, str]
    allowed_paths: tuple[str, ...]
    base_git_commit: str | None = None
    tree_digest: str = field(init=False)
    manifest_digest: str = field(init=False)

    def __post_init__(self):
        identity(self.repo_id, "repo_id")
        _commit(self.base_git_commit)
        if not isinstance(self.files, Mapping) or not 1 <= len(self.files) <= MAX_FILES:
            raise ValueError("files must be a nonempty bounded mapping")
        detached = {}
        spellings = {}
        total = 0
        for name, content in self.files.items():
            _source_path(name)
            if not isinstance(content, str) or any(ord(c) < 32 and c not in "\t\n\r\f" for c in content):
                raise ValueError("only UTF-8 text sources supported")
            try:
                size = len(content.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise ValueError("invalid UTF-8 source") from exc
            total += size
            if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                raise ValueError("source byte limit")
            detached[name] = content
            # Avoid aliases on case-insensitive source/materialization filesystems,
            # including differently spelled directory prefixes across files.
            for length in range(1, len(name.split("/")) + 1):
                prefix = "/".join(name.split("/")[:length])
                key = prefix.lower()
                if key in spellings and spellings[key] != prefix:
                    raise ValueError("case alias in source paths")
                spellings[key] = prefix
        allowed = _paths(self.allowed_paths, "allowed_paths")
        if not set(allowed) <= set(detached):
            raise ValueError("writable paths must be a source subset")
        # A writable source cannot shadow a directory needed by another source.
        for name in detached:
            if any(name.startswith(other + "/") for other in detached if other != name):
                raise ValueError("source file/directory collision")
        object.__setattr__(self, "files", MappingProxyType(dict(sorted(detached.items()))))
        object.__setattr__(self, "allowed_paths", allowed)
        object.__setattr__(self, "tree_digest", tree_digest(detached))
        object.__setattr__(self, "manifest_digest", digest_json(self._unsigned()))

    @classmethod
    def from_files(
        cls, repo_id: str, files: Mapping[str, str], allowed_paths: Sequence[str],
        base_git_commit: str | None = None,
    ) -> FrozenRepository:
        return cls(repo_id, files, _paths(allowed_paths, "allowed_paths"), base_git_commit)

    def _unsigned(self) -> dict:
        return {
            "schema": 1, "repo_id": self.repo_id, "files": dict(self.files),
            "allowed_paths": list(self.allowed_paths), "base_git_commit": self.base_git_commit,
            "tree_digest": self.tree_digest,
        }

    def as_dict(self) -> dict:
        return {**self._unsigned(), "manifest_digest": self.manifest_digest}

    @classmethod
    def from_dict(cls, value: dict) -> FrozenRepository:
        if not isinstance(value, dict) or set(value) != _FIELDS or type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError("unsupported repository manifest schema or fields")
        result = cls.from_files(value["repo_id"], value["files"], value["allowed_paths"], value["base_git_commit"])
        if value["tree_digest"] != result.tree_digest or value["manifest_digest"] != result.manifest_digest:
            raise ValueError("repository manifest integrity mismatch")
        # Require canonical ordered writable capability rather than accepting aliases.
        if value["allowed_paths"] != list(result.allowed_paths):
            raise ValueError("noncanonical allowed_paths")
        return result


def _open_directory(root: str | Path) -> int:
    """Open each absolute component without following even ancestor symlinks."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("safe descriptor-relative intake unavailable")
    if ".." in Path(root).parts:
        raise ValueError("noncanonical repository root")
    absolute = Path(os.path.abspath(root))
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in absolute.parts[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except OSError as exc:
        os.close(fd)
        raise ValueError("repository root or ancestor is unsafe") from exc


def _read_source(root_fd: int, name: str) -> bytes:
    fd = os.dup(root_fd)
    try:
        parts = name.split("/")
        for component in parts[:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        leaf_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf_fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("source must be a regular file")
            if before.st_size > MAX_FILE_BYTES:
                raise ValueError("source file byte limit")
            data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise ValueError("source changed during intake")
            if len(data) > MAX_FILE_BYTES:
                raise ValueError("source file byte limit")
            return data
    except OSError as exc:
        raise ValueError("source traversal or read rejected") from exc
    finally:
        os.close(fd)


def _git_provenance(root: Path, root_fd: int, files: Mapping[str, str], expected: str) -> str:
    """Read-only Git plumbing: no status/diff/filter/hook/FSMonitor execution.

    Only ordinary repositories with an in-root metadata directory are supported;
    gitfiles/worktrees, alternates, grafts and replacement objects are rejected.
    """
    git_fd = None
    try:
        git_fd = os.open(".git", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        for path in ("objects/info/alternates", "objects/info/http-alternates", "info/grafts", "refs/replace"):
            if (root / ".git" / path).exists():
                raise ValueError("unsupported Git object indirection")
        # No symlink in metadata may redirect object/config/ref reads elsewhere.
        count = 0
        for current, directories, names in os.walk(root / ".git", followlinks=False):
            count += len(directories) + len(names)
            if count > 10000 or any((Path(current) / item).is_symlink() for item in directories + names):
                raise ValueError("unsafe or oversized Git metadata")
        env = {
            "PATH": os.defpath, "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
        }
        prefix = [
            "git", "--no-pager", "--no-optional-locks", "--git-dir=" + str(root / ".git"),
            "--work-tree=" + str(root), "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull,
        ]

        def command(*args: str) -> bytes:
            # The source root and metadata must still name the pinned directories.
            for path, descriptor in ((root, root_fd), (root / ".git", git_fd)):
                current = os.stat(path, follow_symlinks=False)
                opened = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                    raise ValueError("Git repository identity changed")
            try:
                result = subprocess.run(prefix + list(args), env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError("Git provenance unavailable") from exc
            if result.returncode or len(result.stdout) > MAX_TOTAL_BYTES * 2:
                raise ValueError("Git provenance rejected")
            return result.stdout

        if command("rev-parse", "--verify", "HEAD").decode("ascii").strip() != expected:
            raise ValueError("Git HEAD differs from expected commit")
        entries = command("ls-tree", "-z", expected, "--", *files).split(b"\x00")
        committed = {}
        for entry in filter(None, entries):
            metadata, name = entry.split(b"\t", 1)
            mode, kind, object_id = metadata.split()
            if mode not in (b"100644", b"100755") or kind != b"blob":
                raise ValueError("selected Git path is not a regular blob")
            committed[name.decode("ascii")] = (mode, object_id)
        if set(committed) != set(files):
            raise ValueError("selected source missing from Git commit")
        index = {}
        for entry in filter(None, command("ls-files", "--stage", "-z", "--", *files).split(b"\x00")):
            metadata, name = entry.split(b"\t", 1)
            mode, object_id, stage = metadata.split()
            if stage != b"0":
                raise ValueError("selected Git index is unmerged")
            index[name.decode("ascii")] = (mode, object_id)
        if index != committed:
            raise ValueError("selected Git index is dirty")
        for name, content in files.items():
            mode, object_id = committed[name]
            # Check size before reading an object into the bounded parent buffer.
            size = command("cat-file", "-s", object_id.decode("ascii"))
            if int(size) != len(content.encode("utf-8")):
                raise ValueError("selected Git source is dirty")
            if command("cat-file", "blob", object_id.decode("ascii")) != content.encode("utf-8"):
                raise ValueError("selected Git source is dirty")
            # Re-read through the pinned root descriptor to detect changes during plumbing.
            if _read_source(root_fd, name) != content.encode("utf-8"):
                raise ValueError("selected Git source changed during provenance")
            # Byte identity deliberately excludes modes, but exact Git provenance
            # still rejects a selected working file whose executable mode changed.
            source_mode = os.stat(root / name, follow_symlinks=False).st_mode
            if bool(source_mode & 0o111) != (mode == b"100755"):
                raise ValueError("selected Git source mode is dirty")
        if command("rev-parse", "--verify", "HEAD").decode("ascii").strip() != expected:
            raise ValueError("Git HEAD changed during provenance")
        return expected
    except (OSError, UnicodeError) as exc:
        raise ValueError("unsupported or unsafe Git provenance") from exc
    finally:
        if git_fd is not None:
            os.close(git_fd)


def freeze_repository(
    root: str | Path, repo_id: str, source_paths: Sequence[str], allowed_paths: Sequence[str],
    expected_commit: str | None = None,
) -> FrozenRepository:
    """Freeze only declared files; writable paths must already be in that snapshot."""
    identity(repo_id, "repo_id")
    paths = _paths(source_paths, "source_paths", nonempty=True)
    allowed = _paths(allowed_paths, "allowed_paths")
    if not set(allowed) <= set(paths):
        raise ValueError("writable paths must be a source subset")
    _commit(expected_commit)
    fd = _open_directory(root)
    try:
        files = {}
        total = 0
        for name in paths:
            data = _read_source(fd, name)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("source total byte limit")
            try:
                files[name] = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("invalid UTF-8 source") from exc
        base_commit = None
        if expected_commit is not None:
            base_commit = _git_provenance(Path(os.path.abspath(root)), fd, files, expected_commit)
        return FrozenRepository.from_files(repo_id, files, allowed, base_commit)
    finally:
        os.close(fd)
