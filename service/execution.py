"""Workspace mechanics and a bounded Linux container backend.

The filesystem helper handles trusted control-plane bytes, not hostile processes.
Docker runs through the configured daemon (a Linux VM on macOS); its safety probes
are evidence only for the tested configuration, never a hostile-tenant certificate.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath

from .artifacts import canonical_bytes, digest_bytes, digest_json


def safe_relative(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise ValueError("invalid relative path")
    parts = PurePosixPath(name).parts
    if (
        name.startswith("/")
        or any(part in {"..", ".git"} for part in parts)
        or str(PurePosixPath(name)) != name
    ):
        raise ValueError("noncanonical or escaping path")
    return name


def tree_digest(files: dict[str, str]) -> str:
    for name, content in files.items():
        safe_relative(name)
        if not isinstance(content, str):
            raise ValueError("only UTF-8 text sources supported")
    return digest_json({"format": "sha256-text-tree-v1", "files": files})


class Workspace:
    def __init__(
        self,
        root: str | Path,
        allowed_paths: list[str],
        max_file_bytes: int = 262144,
        max_total_bytes: int = 2097152,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.allowed = tuple(safe_relative(p) for p in allowed_paths)
        self.max_file, self.max_total = max_file_bytes, max_total_bytes

    def path(self, name: str, write: bool = False) -> Path:
        name = safe_relative(name)
        path = self.root / name
        current = self.root
        for component in PurePosixPath(name).parts:
            current /= component
            if current.is_symlink():
                raise PermissionError("symlink traversal denied")
        if not path.resolve().is_relative_to(self.root):
            raise PermissionError("workspace path escape")
        if write and name not in self.allowed:
            raise PermissionError("write path outside frozen capability")
        return path

    def read(self, name: str) -> dict:
        path = self.path(name)
        with path.open("rb") as stream:
            data = stream.read(self.max_file + 1)
        if len(data) > self.max_file:
            raise ValueError("file byte limit")
        return {"path": name, "text": data.decode("utf-8"), "digest": digest_bytes(data), "bytes": len(data)}

    def replace(self, name: str, expected_digest: str, old: str, new: str) -> dict:
        path = self.path(name, write=True)
        before = self.read(name)
        if before["digest"] != expected_digest:
            raise ValueError("stale edit precondition")
        if not old or before["text"].count(old) != 1:
            raise ValueError("edit anchor must occur exactly once")
        after = before["text"].replace(old, new, 1).encode()
        if len(after) > self.max_file:
            raise ValueError("edited file exceeds bound")
        files = self.snapshot()
        if sum(len(v.encode()) for v in files.values()) - before["bytes"] + len(after) > self.max_total:
            raise ValueError("workspace byte limit")
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(after)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {"path": name, "before_digest": before["digest"], "digest": digest_bytes(after)}

    def snapshot(self) -> dict[str, str]:
        result = {}
        total = 0
        for path in sorted(self.root.rglob("*")):
            if path.is_symlink():
                raise PermissionError("symlink in snapshot")
            if path.is_dir():
                continue
            if not path.is_file():
                raise PermissionError("nonregular source file")
            name = path.relative_to(self.root).as_posix()
            item = self.read(name)
            total += item["bytes"]
            if total > self.max_total:
                raise ValueError("workspace total byte limit")
            result[name] = item["text"]
        return result

    def search(self, query: str, max_hits: int = 40) -> list[dict]:
        if not query or len(query) > 512:
            raise ValueError("invalid literal search query")
        hits = []
        for name, content in self.snapshot().items():
            for line, text in enumerate(content.splitlines(), 1):
                if query in text:
                    hits.append(
                        {
                            "path": name,
                            "line": line,
                            "text": text[:500],
                            "digest": digest_bytes(content.encode()),
                        }
                    )
                    if len(hits) >= max_hits:
                        return hits
        return hits


def materialize(root: str | Path, files: dict[str, str]) -> None:
    tree_digest(files)
    for name, value in files.items():
        path = Path(root) / safe_relative(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def bounded_process(
    argv: list[str], timeout: float = 30, max_output: int = 131072, stdin: bytes | None = None
) -> dict:
    """Run a trusted launcher and retire its owned process group on every return path."""
    start = time.monotonic()
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    pending_input = memoryview(stdin or b"")
    if stdin is not None:
        os.set_blocking(process.stdin.fileno(), False)
        if pending_input:
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        else:
            process.stdin.close()
    output = bytearray()
    reason = "exited"
    try:
        while selector.get_map():
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                reason = "timeout"
                break
            for key, _ in selector.select(min(remaining, 0.1)):
                if key.data == "stdin":
                    try:
                        sent = os.write(key.fd, pending_input[:16384])
                        pending_input = pending_input[sent:]
                    except BrokenPipeError:
                        pending_input = pending_input[:0]
                    if not pending_input:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    continue
                chunk = os.read(key.fd, 16384)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                free = max_output - len(output)
                output.extend(chunk[:free])
                if len(chunk) > free:
                    reason = "output_limit"
                    break
            if reason != "exited":
                break
        if reason == "exited":
            try:
                process.wait(timeout=max(0.001, timeout - (time.monotonic() - start)))
            except subprocess.TimeoutExpired:
                reason = "timeout"
    finally:
        # The leader may have exited and closed stdout while detached-stdio
        # children still hold this owned group. Do not use leader.poll() as
        # evidence of group retirement, or skip escalation when TERM is ignored.
        group_retired = False
        for sig, grace in ((signal.SIGTERM, 0.05), (signal.SIGKILL, 0.5)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                group_retired = True
                break
            except PermissionError:
                # Darwin may transiently report EPERM for orphaned/zombie group
                # membership. Keep polling; EPERM is not proof of retirement.
                pass
            until = time.monotonic() + grace
            while time.monotonic() < until:
                process.poll()  # Reap our leader; orphan children are reaped by init.
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    group_retired = True
                    break
                except PermissionError:
                    pass
                time.sleep(0.005)
            if group_retired:
                break
        process.wait(timeout=5)
        selector.close()
        process.stdout.close()
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
    return {
        "exit_code": process.returncode,
        "reason": reason,
        "output": bytes(output),
        "duration_seconds": time.monotonic() - start,
        "truncated": reason == "output_limit",
        "process_group_retired": group_retired,
    }


def _acknowledged_process_result(result: dict) -> bool:
    """Only complete, normally exited launcher observations grant authority."""
    return (
        type(result.get("exit_code")) is int
        and result["exit_code"] == 0
        and result.get("reason") == "exited"
        and result.get("process_group_retired") is True
        and result.get("truncated") is False
    )


class DockerSandbox:
    """No host mounts/network/credentials. Writable data lives in bounded tmpfs.

    Container removal is confirmed independently of command completion. Keep its
    slot occupied if close() fails. Image must be an immutable locally present ID.
    """

    def __init__(
        self,
        image: str,
        *,
        memory_mb: int = 192,
        cpus: float = 0.5,
        pids: int = 32,
        disk_mb: int = 16,
        timeout: float = 20,
        identity: str | None = None,
        creation_nonce: str | None = None,
        journal_binding=None,
    ):
        if not (image.startswith("sha256:") or "@sha256:" in image):
            raise ValueError("sandbox image must be pinned by digest or local sha256 ID")
        if (
            not 32 <= memory_mb <= 4096
            or not 0 < cpus <= 4
            or not 4 <= pids <= 256
            or not 1 <= disk_mb <= 128
        ):
            raise ValueError("sandbox limits outside reference envelope")
        self.image, self.memory_mb, self.cpus, self.pids, self.disk_mb = image, memory_mb, cpus, pids, disk_mb
        self.timeout = timeout
        if identity is not None and (not identity.isalnum() or len(identity) > 64):
            raise ValueError("invalid infrastructure creation identity")
        self.name = "cam-sandbox-" + (identity or uuid.uuid4().hex)
        self.created = False
        self.provisioning_attempted = False
        self.creation_nonce = uuid.uuid4().hex
        self.container_id = None
        self.create_rejected = False
        self.journal_binding = journal_binding
        if creation_nonce is not None:
            if type(creation_nonce) is not str or not re.fullmatch(r"[0-9a-f]{32}", creation_nonce):
                raise ValueError("invalid durable creation nonce")
            self.creation_nonce = creation_nonce
        if journal_binding is not None:
            from .environment_recovery import EnvironmentBinding, launch_value
            if type(journal_binding) is not EnvironmentBinding or journal_binding.instance["launch"] != launch_value(
                    image, memory_mb=memory_mb, cpus=cpus, pids=pids, disk_mb=disk_mb, timeout=timeout):
                raise ValueError("Docker launch differs from durable create intent")
            self.name = journal_binding.instance["name"]
            if creation_nonce is not None and creation_nonce != journal_binding.instance["creation_nonce"]:
                raise ValueError("Docker nonce differs from durable create intent")
            self.creation_nonce = journal_binding.instance["creation_nonce"]

    def _process(self, args, **kwargs):
        return (self.journal_binding.lifecycle.backend.runner if self.journal_binding is not None else bounded_process)(args, **kwargs)

    def _execution_guard(self):
        if self.journal_binding is not None:
            self.journal_binding.assert_execution()

    def _bind_container(self, container_id: str):
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise RuntimeError("container ownership unresolved: invalid immutable ID")
        if self.journal_binding is not None:
            self.journal_binding.bind(container_id)
            self.container_id = container_id
            return
        inspected = bounded_process(["docker", "inspect", container_id, "--format", "{{json .}}"], timeout=30)
        try:
            details = json.loads(inspected["output"])
        except (ValueError, TypeError) as exc:
            raise RuntimeError("container ownership unresolved: invalid inspection") from exc
        if (
            not _acknowledged_process_result(inspected)
            or details.get("Id") != container_id
            or details.get("Name") != "/" + self.name
            or details.get("Config", {}).get("Labels", {}).get("coding-agent-mastery-create-nonce")
            != self.creation_nonce
        ):
            raise RuntimeError("container ownership unresolved: instance nonce mismatch")
        if self.container_id is not None and self.container_id != container_id:
            raise RuntimeError("container instance cannot change")
        self.container_id = container_id

    def _recover_owned_instance(self):
        # Name is diagnostic only. The instance-specific nonce must match before
        # an uncertain create can grant authority to remove any container.
        probe = bounded_process(
            [
                "docker",
                "ps",
                "-a",
                "--no-trunc",
                "--filter",
                "label=coding-agent-mastery-create-nonce=" + self.creation_nonce,
                "--format",
                "{{.ID}}",
            ],
            timeout=30,
        )
        ids = probe["output"].decode(errors="replace").split()
        if not _acknowledged_process_result(probe) or len(ids) != 1:
            raise RuntimeError(
                "unacknowledged provisioning is unresolved; absence may precede delayed create"
            )
        self._bind_container(ids[0])

    def start(self, files: dict[str, str]):
        if self.journal_binding is not None and self.journal_binding.grant["duplicate"]:
            raise RuntimeError("durable create intent already admitted; reconciliation required")
        if self.provisioning_attempted or self.create_rejected or self.container_id is not None:
            raise RuntimeError("sandbox creation instance is single-use")
        files = dict(files)
        if sum(len(value.encode()) for value in files.values()) > 2 * 1024 * 1024:
            raise ValueError("sandbox source byte limit")
        tree_digest(files)
        if self.journal_binding is not None:
            source = self.journal_binding.lifecycle.row()["environment_journal"]["source"]
            if digest_json(files) != source["input_digest"]:
                raise ValueError("Docker input differs from journaled exact copied source")
        args = [
            "docker",
            "create",
            "--pull=never",
            "--name",
            self.name,
            "--label",
            "coding-agent-mastery=disposable",
            "--label",
            "coding-agent-mastery-create-nonce=" + self.creation_nonce,
            "--network=none",
            "--read-only",
            "--user=65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--memory={self.memory_mb}m",
            f"--memory-swap={self.memory_mb}m",
            f"--cpus={self.cpus}",
            f"--pids-limit={self.pids}",
            "--ulimit=nofile=128:128",
            "--ulimit=fsize=8388608:8388608",
            "--log-driver=none",
            "--tmpfs",
            f"/workspace:rw,nosuid,nodev,size={self.disk_mb}m,mode=1777",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
            "--workdir=/workspace",
            "--entrypoint=python",
            self.image,
            "-I",
            "-c",
            "import time; time.sleep(3600)",
        ]
        self.provisioning_attempted = True
        self._execution_guard()
        result = self._process(args, timeout=30)
        if not _acknowledged_process_result(result):
            message = result["output"].decode(errors="replace")
            if (
                type(result.get("exit_code")) is int and result["exit_code"] != 0
                and result.get("reason") == "exited"
                and result.get("process_group_retired") is True
                and result.get("truncated") is False
                and "Conflict" in message and "already in use" in message
            ):
                # An acknowledged name conflict owns no instance and cannot clean
                # the existing container merely because its name matches.
                if self.journal_binding is not None:
                    self.journal_binding.reject()
                self.create_rejected = True
                self.provisioning_attempted = False
                raise RuntimeError(message)
            try:
                self.close()
            except RuntimeError as cleanup_error:
                raise RuntimeError(
                    "container provisioning/retirement unknown: " + self.name
                ) from cleanup_error
            raise RuntimeError(message)
        try:
            self._bind_container(result["output"].decode().strip())
        except Exception:
            # Leave attempted provisioning visible for nonce-based reconciliation.
            raise
        self.created = True
        try:
            self._execution_guard()
            start = self._process(["docker", "start", self.container_id], timeout=30)
            if not _acknowledged_process_result(start):
                raise RuntimeError("container did not start")
            writer = (
                "import sys,json,pathlib; files=json.load(sys.stdin); "
                "[(pathlib.Path(p).parent.mkdir(parents=True,exist_ok=True), "
                "pathlib.Path(p).write_text(v,encoding='utf-8')) for p,v in files.items()]"
            )
            self._execution_guard()
            copied = self._process(
                [
                    "docker",
                    "exec",
                    "-i",
                    "--workdir=/workspace",
                    self.container_id,
                    "python",
                    "-I",
                    "-c",
                    writer,
                ],
                stdin=canonical_bytes(files),
                timeout=30,
            )
            if not _acknowledged_process_result(copied):
                raise RuntimeError("sandbox input copy failed: " + copied["output"].decode(errors="replace"))
        except Exception:
            self.close()
            raise
        return self

    def run(self, argv: list[str], max_output: int = 131072) -> dict:
        if not self.created or not argv or any(not isinstance(x, str) or "\x00" in x for x in argv):
            raise ValueError("invalid sandbox command")
        self._execution_guard()
        result = self._process(
            [
                "docker",
                "exec",
                "--workdir=/workspace",
                self.container_id,
                "env",
                "-i",
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "HOME=/tmp",
                *argv,
            ],
            timeout=self.timeout,
            max_output=max_output,
        )
        if (
            result.get("reason") != "exited"
            or result.get("process_group_retired") is not True
            or result.get("truncated") is not False
        ):
            # Killing the docker client is not proof its remote process stopped.
            self.close()
        result["output"] = result["output"].decode("utf-8", errors="replace")
        return result

    def close(self) -> dict:
        if self.journal_binding is not None:
            result = self.journal_binding.close()
            self.created = self.provisioning_attempted = False
            return result
        if not self.provisioning_attempted:
            return {
                "retired": True,
                "container": self.name,
                "container_id": self.container_id,
                "evidence": "no owned provisioning instance"
                if self.create_rejected
                else "not provisioned or previously retired",
            }
        if self.container_id is None:
            self._recover_owned_instance()
        # Cleanup authority is the immutable owned instance ID, never its name.
        removed = bounded_process(["docker", "rm", "--force", self.container_id], timeout=30)
        inspected = bounded_process(
            [
                "docker",
                "ps",
                "-a",
                "--no-trunc",
                "--filter",
                "id=" + self.container_id,
                "--format",
                "{{.ID}}",
            ],
            timeout=30,
        )
        retired = _acknowledged_process_result(inspected) and not inspected["output"].strip()
        if not retired:
            raise RuntimeError("container retirement unknown; retain physical slot")
        self.created = False
        self.provisioning_attempted = False
        return {
            "retired": True,
            "container": self.name,
            "container_id": self.container_id,
            "creation_nonce": self.creation_nonce,
            "removal_acknowledged": _acknowledged_process_result(removed),
            "evidence": "owned immutable container ID absent from acknowledged inventory",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
