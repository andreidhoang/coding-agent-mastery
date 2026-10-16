"""Run this repository's checks; optional integrations require explicit env.

Subprocess output is hashed/summarized, never copied to the result or console:
tracebacks may contain private connection details. No secrets or external URLs
are written. The process group created here is the only timeout cleanup target.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def integration_flags():
    postgres = os.environ.get("CAM_TEST_POSTGRES_URL")
    if postgres:
        try:
            parsed = urlsplit(postgres)
            local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        except ValueError:
            local = False
        if not local or not parsed.scheme.startswith("postgresql") or parsed.query:
            raise ValueError("CAM_TEST_POSTGRES_URL must identify an explicit disposable loopback PostgreSQL database")
    image = os.environ.get("CAM_TEST_SANDBOX_IMAGE")
    if image and not re.fullmatch(r"[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("CAM_TEST_SANDBOX_IMAGE must be an explicitly selected digest-pinned image")
    if image:
        try:
            probe = subprocess.run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                                   capture_output=True, text=True, timeout=10, check=False)
            endpoint = probe.stdout.strip()
            local_docker = endpoint.startswith(("unix://", "npipe://")) or (
                urlsplit(endpoint).hostname in {"localhost", "127.0.0.1", "::1"})
        except (OSError, ValueError, subprocess.TimeoutExpired):
            local_docker = False
        # DOCKER_HOST overrides the selected context's endpoint.
        override = os.environ.get("DOCKER_HOST")
        if override:
            local_docker = override.startswith(("unix://", "npipe://")) or urlsplit(override).hostname in {"localhost", "127.0.0.1", "::1"}
        if not local_docker:
            raise ValueError("Docker integration requires an explicitly local daemon/context")
    temporal = os.environ.get("CAM_TEST_TEMPORAL", "0")
    if temporal not in {"0", "1", ""}:
        raise ValueError("CAM_TEST_TEMPORAL must be 0 or 1")
    return {"postgres": bool(postgres), "docker": bool(image), "temporal": temporal == "1"}


def versions():
    packages = {}
    for name in ("pytest", "ruff", "sqlalchemy", "fastapi", "httpx", "uvicorn", "psycopg", "temporalio", "torch"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "platform": platform.system(),
            "architecture": platform.machine(), "packages": packages}


def _terminate_owned_process(process):
    """Retire a just-created session's group, independently of its leader.

    The caller creates this POSIX group with start_new_session=True and records
    its ID as process.pid. This is launcher cleanup, not containment: children
    that deliberately escape the group require a separate execution boundary.
    On Windows only the direct process is retired; no job-object tree is claimed.
    """
    if os.name == "posix":
        group_id = process.pid

        def group_exists():
            try:
                os.killpg(group_id, 0)
            except ProcessLookupError:
                return False
            return True

        def send_group(signum):
            try:
                os.killpg(group_id, signum)
            except ProcessLookupError:
                pass  # The group can disappear between observation and signal.

        send_group(signal.SIGTERM)
        deadline = time.monotonic() + 5
        while group_exists() and time.monotonic() < deadline:
            process.poll()  # Reap the leader without assuming children exited.
            time.sleep(0.02)
        if group_exists():
            send_group(signal.SIGKILL)
        process.wait(timeout=5)
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_check(name, command, timeout):
    started = time.monotonic()
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    # Disable unrelated user pytest plugins; this suite requires no plugin.
    with tempfile.TemporaryFile() as capture:
        process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                   stdout=capture, stderr=subprocess.STDOUT,
                                   start_new_session=os.name == "posix")
        timed_out = False
        interrupted = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_owned_process(process)
        except KeyboardInterrupt:
            interrupted = True
            _terminate_owned_process(process)
        capture.seek(0)
        hasher = hashlib.sha256()
        tail = b""
        size = 0
        for chunk in iter(lambda: capture.read(65536), b""):
            hasher.update(chunk)
            size += len(chunk)
            tail = (tail + chunk)[-16384:]
    summary = {}
    if name == "pytest":
        for count, category in re.findall(rb"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed)", tail):
            summary[category.decode()] = int(count)
    return {"check": name, "status": "interrupted" if interrupted else "timed_out" if timed_out else "passed" if process.returncode == 0 else "failed",
            "exit_code": process.returncode, "elapsed_seconds": round(time.monotonic() - started, 3),
            "captured_output_bytes": size, "captured_output_sha256": hasher.hexdigest(),
            "output_retained": False, "counts": summary,
            "resource_cleanup": "test-owned fixtures; inspect uncertain resources after timeout/interruption" if timed_out or interrupted else "delegated to scoped test fixtures"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="show redacted validation plan without running checks")
    parser.add_argument("--output", type=Path, help="fresh JSON result path; existing files are never overwritten")
    parser.add_argument("--timeout", type=int, default=1200, help="maximum seconds per check")
    args = parser.parse_args(argv)
    if not 10 <= args.timeout <= 7200:
        parser.error("timeout must be 10..7200 seconds")
    try:
        flags = integration_flags()
    except ValueError as error:
        parser.error(str(error))
    checks = [("ruff", [sys.executable, "-m", "ruff", "check", "service", "evals", "compute", "workloads", "tests", "scripts"]),
              ("pytest", [sys.executable, "-m", "pytest", "tests", "-q"])]
    report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "mode": "plan_only" if args.plan else "local_validation", "versions": versions(),
              "integrations": flags, "check_names": [name for name, _ in checks],
              "secret_values_recorded": False, "live_inference": "disabled",
              "hosted_deployment": "not_performed", "human_mastery": "not_assessed"}
    if args.plan:
        print(json.dumps(report, indent=2))
        return 0
    output = args.output or ROOT / ".runtime" / "checks" / ("check-" + uuid.uuid4().hex + ".json")
    if output.exists() or output.is_symlink():
        parser.error("output must be a fresh path")
    results = []
    for name, command in checks:
        print(json.dumps({"check": name, "state": "started"}), flush=True)
        try:
            result = run_check(name, command, args.timeout)
        except OSError:
            result = {"check": name, "status": "unavailable", "error": "cannot launch selected Python check"}
        results.append(result)
        print(json.dumps(result), flush=True)
        if result["status"] == "interrupted":
            break
    report["results"] = results
    report["passed"] = all(result["status"] == "passed" for result in results)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"report": str(output.resolve()), "passed": report["passed"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
