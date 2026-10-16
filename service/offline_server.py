"""Explicit loopback composition of the existing authored-fixture runtime."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading
import time

import sqlalchemy as sa

from .api import APIError, create_app
from .admission import persisted_admission_policy
from .artifacts import LocalArtifacts, canonical_bytes, digest_bytes
from .contracts import freeze
from .engine import ReferenceEngine
from .serving_config import (
    config_identity, fixture_contract, load_tokens, principal_value, read_json_file, safe_path, validate_config,
)
from .storage import RuntimeStore, SCHEMA_VERSION, TABLES, schema_versions
from .workflows import LocalOutboxDispatcher

SENTINEL = b"coding-agent-mastery offline fixture artifact probe v1\n"
SENTINEL_SCOPE = ("serving-probe", "sentinel-v1")


def _write_new(path, value):
    path = safe_path(str(path))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def _store(config, artifacts):
    return RuntimeStore("sqlite:///" + str(Path(config["root"]) / "authority.sqlite"), artifacts,
                        **config["limits"], admission_policy=config["admission_policy"])


def _effective_policy(store, config):
    with store._read() as connection:
        if connection.execute(sa.select(schema_versions.c.version)).scalars().all() != [SCHEMA_VERSION]:
            raise ValueError("authority schema changed")
    state = store.service_state()
    if any(state.get(key) != value for key, value in config["limits"].items()):
        raise ValueError("effective operating limits differ from serving configuration")
    if persisted_admission_policy(state) != config["admission_policy"]:
        raise ValueError("effective admission policy differs from serving configuration")
    if state["quarantined"] or not state["execution_enabled"]:
        raise ValueError("reconciliation_required")
    return state


def _startup_frontier(store, config):
    """Bounded read-only classification; elapsed leases cannot retire work."""
    allowed = {canonical_bytes(item) for item in config["catalog"]}
    with store._read() as connection:
        tasks = TABLES["tasks"]
        rows = connection.execute(sa.select(tasks.c.data).where(
            tasks.c.data["execution_state"].as_string().in_(("queued", "running"))
        ).limit(config["admission_policy"]["service_pending_limit"] + 1)).scalars().all()
        if len(rows) > config["admission_policy"]["service_pending_limit"]:
            raise ValueError("reconciliation_required")
        for task in rows:
            if task["execution_state"] != "queued" or canonical_bytes(task["contract"]) not in allowed:
                raise ValueError("reconciliation_required")
            # Queued means unstarted, not simply a convenient task label.
            for name in ("attempts", "dispatches", "checkpoints", "candidates"):
                table = TABLES[name]
                if connection.execute(sa.select(table.c.id).where(
                    table.c.tenant_id == task["tenant_id"], table.c.task_id == task["task_id"]
                ).limit(1)).first() is not None:
                    raise ValueError("reconciliation_required")
        dispatches = TABLES["dispatches"]
        unresolved = sa.or_(dispatches.c.data["effect_state"].as_string().in_(("in_flight", "unknown")),
                            dispatches.c.data["billing_state"].as_string() != "settled")
        if connection.execute(sa.select(dispatches.c.id).where(unresolved).limit(1)).first() is not None:
            raise ValueError("reconciliation_required")
        sandboxes = TABLES["sandboxes"]
        if connection.execute(sa.select(sandboxes.c.id).where(
            sandboxes.c.data["status"].as_string() != "retired"
        ).limit(1)).first() is not None:
            raise ValueError("reconciliation_required")


class OfflineService:
    """One root lock, one serial child, existing transactional domain owners."""

    def __init__(self, config, tokens):
        self.config = validate_config(config)
        self.tokens = dict(tokens)
        if (any(not isinstance(token, str) or not 24 <= len(token) <= 512 for token in self.tokens)
                or len(self.tokens) != len(self.config["principals"])
                or set(self.tokens.values()) != {principal_value(entry) for entry in self.config["principals"]}):
            raise ValueError("credential bindings differ from configured principals")
        self.root = safe_path(self.config["root"], directory=True)
        self.identity = config_identity(self.config)
        self.store = self.artifacts = self.worker = None
        self.lock_fd = self.control_fd = None
        self.worker_state = "startup"
        self.current_task = None
        self.stopping = False
        self.monitor = None
        self._state_lock = threading.Lock()
        self.incarnation = None

    def start(self):
        if self.store is not None or self.worker is not None:
            raise ValueError("service instance is single-use")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        safe_path(str(self.root), directory=True)
        lock = safe_path(str(self.root / "service.lock"))
        self.lock_fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(self.lock_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("invalid service lock")
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            marker = self.root / "service-identity.json"
            fresh = not marker.exists()
            for name in ("authority.sqlite", "authority.sqlite-wal", "authority.sqlite-shm",
                         "worker-config.json", "service-identity.json"):
                safe_path(str(self.root / name))
            for name in ("artifacts", "workspaces"):
                safe_path(str(self.root / name), directory=True)
            if fresh and (self.root / "authority.sqlite").exists():
                raise ValueError("existing authority store has no serving identity")
            if not fresh and (not (self.root / "authority.sqlite").is_file()
                              or (self.root / "authority.sqlite").stat().st_size == 0):
                raise ValueError("configured authority store is missing or empty")
            saved_marker = None if fresh else read_json_file(marker, max_bytes=1024)
            if not fresh and (not isinstance(saved_marker, dict)
                              or set(saved_marker) != {"schema", "config_digest", "service_incarnation"}
                              or type(saved_marker["schema"]) is not int or saved_marker["schema"] != 1
                              or saved_marker["config_digest"] != self.identity
                              or not isinstance(saved_marker["service_incarnation"], str)):
                raise ValueError("serving root configuration identity changed")
            self.artifacts = LocalArtifacts(self.root / "artifacts")
            self.store = _store(self.config, self.artifacts)
            state = _effective_policy(self.store, self.config)
            self.incarnation = state["service_incarnation"]
            if not fresh and saved_marker["service_incarnation"] != self.incarnation:
                raise ValueError("serving root authority identity changed")
            _startup_frontier(self.store, self.config)
            if fresh:
                self.artifacts.put(*SENTINEL_SCOPE, SENTINEL)
                _write_new(self.root / "worker-config.json", self.config)
                _write_new(marker, {"schema": 1, "config_digest": self.identity,
                                    "service_incarnation": self.incarnation})
            elif read_json_file(self.root / "worker-config.json") != self.config:
                raise ValueError("worker configuration identity changed")
            self._probe_artifacts()
            self.store.set_admission(False)
            child_read, self.control_fd = os.pipe()
            try:
                self.worker = subprocess.Popen(
                    [sys.executable, "-I", "-m", "service.offline_server", "_worker", "--config",
                     str(self.root / "worker-config.json"), "--lock-fd", str(self.lock_fd),
                     "--control-fd", str(child_read)],
                    cwd=self.root, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                                       "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    pass_fds=(self.lock_fd, child_read), start_new_session=True,
                )
            finally:
                os.close(child_read)
            self.monitor = threading.Thread(target=self._monitor, name="offline-fixture-supervisor", daemon=True)
            self.monitor.start()
            deadline = time.monotonic() + 15
            while self.worker_state == "startup" and self.worker.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            if self.worker_state not in {"idle", "busy"} or self.worker.poll() is not None:
                raise ValueError("worker startup failed")
            self.store.set_admission(True)
        except BaseException:
            self.stop()
            raise

    def _monitor(self):
        try:
            while True:
                line = self.worker.stdout.readline(4097)
                if not line:
                    break
                if len(line) > 4096 or not line.endswith(b"\n"):
                    raise ValueError("invalid worker observation")
                message = json.loads(line)
                if not isinstance(message, dict) or set(message) != {"state", "task_id"}:
                    raise ValueError("invalid worker observation")
                if message["state"] not in {"idle", "busy", "failed", "stopped"}:
                    raise ValueError("invalid worker observation")
                task = message["task_id"]
                if task is not None and (not isinstance(task, str) or len(task) > 128):
                    raise ValueError("invalid worker task identity")
                with self._state_lock:
                    self.worker_state, self.current_task = message["state"], task
                if message["state"] == "failed":
                    self.store.set_admission(False)
        except Exception:
            with self._state_lock:
                self.worker_state = "failed"
        finally:
            if not self.stopping:
                with self._state_lock:
                    self.worker_state = "failed"
                try:
                    self.store.set_admission(False)
                except Exception:
                    pass

    def _probe_artifacts(self):
        if self.artifacts.get(*SENTINEL_SCOPE, digest_bytes(SENTINEL), max_bytes=256) != SENTINEL:
            raise ValueError("artifact sentinel mismatch")

    def readiness(self):
        reason = None
        with self._state_lock:
            worker_state = self.worker_state
        if self.stopping:
            reason = "stopping"
        elif self.store is None:
            reason = "startup_incomplete"
        elif self.worker is None or self.worker.poll() is not None or worker_state not in {"idle", "busy"}:
            reason = "worker_unavailable"
        else:
            try:
                state = _effective_policy(self.store, self.config)
                if state["service_incarnation"] != self.incarnation or not state["accept_new_tasks"]:
                    reason = "authority_unavailable"
                if read_json_file(self.root / "service-identity.json", max_bytes=1024) != {
                    "schema": 1, "config_digest": self.identity, "service_incarnation": self.incarnation
                }:
                    reason = "configuration_mismatch"
                self._probe_artifacts()
                from workloads import validate_assets
                validate_assets()
            except Exception:
                reason = "dependency_unavailable"
        return {"ready": reason is None, "reason": reason, "mode": "offline_fixture_v1",
                "config_digest": self.identity, "worker": worker_state,
                "production_readiness": "unmeasured", "live_inference": "disabled"}

    def admission(self, _principal, contract):
        if canonical_bytes(contract) not in {canonical_bytes(item) for item in self.config["catalog"]}:
            raise APIError(422, "unsupported_fixture_contract", "exact prepared fixture contract required")

    def catalog(self, principal):
        return {"contracts": [freeze(c) for c in self.config["catalog"] if c["repo_id"] in principal.repositories]}

    def stop(self):
        self.stopping = True
        if self.store is not None:
            try:
                self.store.set_admission(False)
            except Exception:
                pass
        if self.control_fd is not None:
            os.close(self.control_fd)
            self.control_fd = None
        if self.worker is not None:
            try:
                self.worker.wait(timeout=self.config["worker"]["shutdown_seconds"])
            except subprocess.TimeoutExpired:
                os.killpg(self.worker.pid, signal.SIGTERM)
                try:
                    self.worker.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(self.worker.pid, signal.SIGKILL)
                    self.worker.wait(timeout=2)
            if self.monitor is not None:
                self.monitor.join(timeout=2)
            self.worker.stdout.close()
        if self.store is not None:
            self.store.close()
        if self.lock_fd is not None:
            # Close, do not explicitly unlock a descriptor inherited by a still-live child.
            os.close(self.lock_fd)
            self.lock_fd = None

    def app(self):
        @asynccontextmanager
        async def lifespan(_app):
            import asyncio
            await asyncio.to_thread(self.start)
            try:
                yield
            finally:
                await asyncio.to_thread(self.stop)

        # Store construction belongs to startup; delegate calls only after lifespan start.
        service = self

        class StoreProxy:
            def __getattr__(self, name):
                if service.store is None:
                    raise RuntimeError("service startup incomplete")
                return getattr(service.store, name)

        class ArtifactProxy:
            def __getattr__(self, name):
                if service.artifacts is None:
                    raise RuntimeError("service startup incomplete")
                return getattr(service.artifacts, name)

        return create_app(StoreProxy(), tokens=self.tokens, artifact_store=ArtifactProxy(),
                          contract_admission=self.admission, contract_catalog=self.catalog,
                          readiness=self.readiness, lifespan=lifespan)


def _worker(config_path, lock_fd, control_fd):
    config = validate_config(read_json_file(config_path))
    root = Path(config["root"])
    expected = (root / "service.lock").stat()
    actual = os.fstat(lock_fd)
    if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
        raise ValueError("worker ownership descriptor mismatch")
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.set_blocking(control_fd, False)
    artifacts = LocalArtifacts(root / "artifacts")
    store = _store(config, artifacts)
    engine = ReferenceEngine(store, artifacts, root / "workspaces")

    def observed(state, task=None):
        print(json.dumps({"state": state, "task_id": task}), flush=True)

    def run(tenant, task):
        observed("busy", task)
        result = engine.run_task(tenant, task)
        observed("idle")
        return result

    try:
        _effective_policy(store, config)
        _startup_frontier(store, config)
        dispatcher = LocalOutboxDispatcher(store, run)
        observed("idle")
        while True:
            try:
                if os.read(control_fd, 1) == b"":
                    break
            except BlockingIOError:
                pass
            result = dispatcher.dispatch_once(limit=1)
            if any(item["status"] == "pending_retry" for item in result):
                observed("failed")
                return 2
            time.sleep(config["worker"]["poll_ms"] / 1000)
        observed("stopped")
        return 0
    finally:
        store.close()
        os.close(control_fd)
        os.close(lock_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit offline fixture service; no paid execution")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for name in ("config", "root", "workload"):
        prepare.add_argument("--" + name, required=True)
    prepare.add_argument("--port", type=int, required=True)
    prepare.add_argument("--execution-deadline", type=float, required=True)
    prepare.add_argument("--review-deadline", type=float, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--config", required=True)
    worker = commands.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--config", required=True)
    worker.add_argument("--lock-fd", type=int, required=True)
    worker.add_argument("--control-fd", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            contract = fixture_contract(args.workload, args.execution_deadline, args.review_deadline)
            config = validate_config({
                "schema": 1, "mode": "offline_fixture_v1", "root": args.root,
                "host": "127.0.0.1", "port": args.port,
                "limits": {"service_slot_limit": 3, "tenant_slot_limit": 3,
                           "service_budget_units": 100000, "tenant_budget_units": 100000},
                "admission_policy": {"schema": 1, "service_pending_limit": 4, "tenant_pending_limit": 2},
                "worker": {"poll_ms": 100, "shutdown_seconds": 10},
                "principals": [{"tenant_id": "demo", "subject_id": "local-operator",
                                "repositories": [contract["repo_id"]], "can_review": True,
                                "profiles": ["production"], "token_env": "CAM_SERVE_TOKEN_LOCAL"}],
                "catalog": [contract],
            })
            _write_new(Path(args.config), config)
            print(json.dumps({"status": "prepared", "config_digest": config_identity(config),
                              "live_inference": "disabled"}))
            return 0
        if args.command == "_worker":
            return _worker(args.config, args.lock_fd, args.control_fd)
        config = validate_config(read_json_file(args.config))
        service = OfflineService(config, load_tokens(config, os.environ))
        import uvicorn
        uvicorn.run(service.app(), host=config["host"], port=config["port"], access_log=False,
                    log_level="error", timeout_keep_alive=5, limit_concurrency=32,
                    timeout_graceful_shutdown=config["worker"]["shutdown_seconds"] + 5)
        return 0
    except Exception:
        # Exception text can contain operator paths or credential-bearing input.
        print(json.dumps({"status": "refused", "reason": "invalid_configuration_or_lifecycle",
                          "live_inference": "disabled"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
