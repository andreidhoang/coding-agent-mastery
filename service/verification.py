"""Protected supervisor judges behavior, never a candidate-authored PASS marker.

The Linux adapter exposes an RPC-shaped tracker object to the frozen grader. The
grader runs in the trusted supervisor; each candidate operation runs in Docker.
The candidate can forge its own replies (as any implementation can return values),
but cannot mutate the expected outputs or create a supervisor receipt.
"""

from __future__ import annotations

import json
import types
import uuid
from pathlib import Path

from .artifacts import digest_json, digest_bytes
from . import execution as execution_module
from .execution import DockerSandbox, tree_digest, bounded_process, _acknowledged_process_result
from .protocol import strict_json

RPC_SOURCE = r"""
import importlib.util, json, sys
request = json.loads(sys.argv[1])
def load(name):
    spec = importlib.util.spec_from_file_location(name, '/workspace/' + name + '.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
try:
    tracker = load('issue_tracker')
    instance = tracker.IssueTracker(request['database'])
    try:
        if request['method'] == '__count_events__':
            value = instance.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        elif request['method'] == '__init__':
            value = None
        elif request['method'] == '__client_import__':
            client = load('client').ImportClient(instance)
            value = client.import_csv(*request['args'], **request['kwargs'])
        elif request['method'] == '__client_submit__':
            client = load('client').ImportClient(instance)
            value = client.submit(*request['args'], **request['kwargs'])
        else:
            allowed = {'submit_import','process_batch','status','list_issues','cancel','progress','_cursor'}
            if request['method'] not in allowed:
                raise ValueError('unknown candidate operation')
            value = getattr(instance, request['method'])(*request['args'], **request['kwargs'])
    finally:
        instance.close()
    print(json.dumps({'ok':True,'value':value}, separators=(',',':'), allow_nan=False))
except Exception as error:
    print(json.dumps({'ok':False,'error_type':type(error).__name__,'message':str(error)[:500]}))
"""


class RPCBoundaryError(Exception):
    """Transport/schema failure is not a candidate application exception."""


class Conflict(Exception):
    pass


class InvalidCursor(Exception):
    pass


def _grader():
    from workloads.registry import _trusted_module, validate_assets

    validate_assets()
    return _trusted_module("oracle/fixtures/acceptance.py")


class FixtureVerifier:
    """CPU default only executes exact pre-authored controls from their locked paths."""

    environment_digest = digest_json({"mode": "trusted-frozen-control", "schema": 1})

    def verify(self, files: dict[str, str], task_definition, sandbox_id: str | None = None) -> dict:
        from workloads.registry import ROOT, TARGET_FILES, _trusted_module, validate_assets

        files = dict(files)
        verified_digest = tree_digest(files)
        validate_assets()
        identities = {
            "tree_digest": verified_digest,
            "grader_digest": task_definition.as_dict()["grader_sha256"],
            "environment_digest": self.environment_digest,
        }
        choices = [
            "oracle/reference",
            f"baseline/{task_definition.baseline_id}",
            f"oracle/incorrect/{task_definition.baseline_id}",
        ]
        selected = None
        for choice in choices:
            expected = {name: (ROOT / choice / name).read_text() for name in TARGET_FILES}
            if expected == files:
                selected = choice
                break
        if selected is None:
            return {
                "passed": False,
                "criteria": [],
                "cause": "arbitrary_candidate_requires_linux",
                **identities,
                "mode": "trusted_frozen_controls_only",
            }
        result = _grader().grade(
            task_definition.requirements,
            _trusted_module(f"{selected}/issue_tracker.py"),
            _trusted_module(f"{selected}/client.py"),
            task_definition.variant,
        )
        return {
            **result,
            **identities,
            "mode": "trusted_frozen_controls_only",
        }


class LinuxVerifier:
    def __init__(self, image: str):
        self.image = image
        resolved = bounded_process(
            ["docker", "image", "inspect", image, "--format", "{{.Id}} {{.Architecture}} {{.Os}}"], timeout=20
        )
        if not _acknowledged_process_result(resolved):
            raise ValueError("verification requires an already present immutable image")
        image_id, architecture, system = resolved["output"].decode().strip().split()
        if system != "linux":
            raise ValueError("Linux verification image required")
        self.environment_digest = digest_json(
            {
                "schema": 1,
                "image": image,
                "image_config_id": image_id,
                "architecture": architecture,
                "os": system,
                "network": "none",
                "memory_mb": 192,
                "cpus": 0.5,
                "pids": 32,
                "disk_mb": 16,
                "rpc": digest_json(RPC_SOURCE),
                "controller": digest_bytes(Path(__file__).read_bytes()),
                "execution": digest_bytes(Path(execution_module.__file__).read_bytes()),
            }
        )

    def verify(self, files: dict[str, str], task_definition, sandbox_id: str | None = None, lifecycle=None) -> dict:
        files = dict(files)
        verified_digest = tree_digest(files)
        if set(files) != {"issue_tracker.py", "client.py"}:
            raise ValueError("verifier only supports frozen issue-tracker protocol")
        from workloads.registry import validate_assets

        validate_assets()
        observations = []
        boundary_failures = []
        database_paths: dict[str, str] = {}
        binding = None
        if lifecycle is not None:
            from .environment_recovery import launch_value
            source = lifecycle.source(purpose="fixture", tree_digest=verified_digest, input_digest=digest_json(files),
                                      grader_digest=task_definition.as_dict()["grader_sha256"],
                                      environment_digest=self.environment_digest)
            binding = lifecycle.instance(ordinal=0, source=source, launch=launch_value(self.image), max_instances=1)
        sandbox = DockerSandbox(self.image, identity=sandbox_id, **({"journal_binding": binding} if binding is not None else {}))

        def boundary_error(message: str, cause: Exception | None = None):
            boundary_failures.append({"cause": message})
            raise RPCBoundaryError(message) from cause

        def rpc(database: str, method: str, *args, **kwargs):
            if boundary_failures:
                raise RPCBoundaryError("candidate RPC boundary already failed")
            request = {"database": database, "method": method, "args": args, "kwargs": kwargs}
            try:
                result = sandbox.run(
                    ["python", "-I", "-c", RPC_SOURCE, json.dumps(request)], max_output=65536
                )
            except Exception as exc:
                boundary_error("candidate transport failed", exc)
            observations.append(
                {
                    "request_digest": digest_json(request),
                    "method": method,
                    "exit_code": result["exit_code"],
                    "reason": result["reason"],
                    "duration_seconds": result["duration_seconds"],
                    "output_digest": digest_json(result["output"]),
                }
            )
            if result["exit_code"] != 0 or result["reason"] != "exited":
                boundary_error("candidate operation terminated without a complete response")
            try:
                response = strict_json(result["output"])
            except Exception as exc:
                boundary_error("candidate RPC response is malformed", exc)
            if not isinstance(response, dict) or type(response.get("ok")) is not bool:
                boundary_error("candidate RPC schema error")
            if response["ok"]:
                if set(response) != {"ok", "value"}:
                    boundary_error("candidate RPC success schema error")
                return response["value"]
            if (
                set(response) != {"ok", "error_type", "message"}
                or not isinstance(response["error_type"], str)
                or not isinstance(response["message"], str)
            ):
                boundary_error("candidate RPC exception schema error")
            exceptions = {
                "Conflict": Conflict,
                "InvalidCursor": InvalidCursor,
                "KeyError": KeyError,
                "ValueError": ValueError,
                "RuntimeError": RuntimeError,
            }
            # Only a complete, valid application-exception envelope may reach
            # the grader's expected-exception oracle. Boundary failures latch.
            raise exceptions.get(response["error_type"], Exception)(response["message"])

        class DatabaseProxy:
            def __init__(self, database):
                self.database = database

            def execute(self, statement):
                if statement != "SELECT COUNT(*) FROM events":
                    raise ValueError("grader requested unsupported query")
                value = rpc(self.database, "__count_events__")
                return types.SimpleNamespace(fetchone=lambda: (value,))

        class TrackerProxy:
            def __init__(self, database=":memory:"):
                identity = uuid.uuid4().hex if database == ":memory:" else database
                self.database = database_paths.setdefault(
                    identity, "/tmp/tracker-" + uuid.uuid4().hex + ".sqlite"
                )
                self.db = DatabaseProxy(self.database)
                rpc(self.database, "__init__")

            def close(self):
                # Each RPC closes its actual DB connection; file persists for reopen checks.
                return None

            def __getattr__(self, method):
                return lambda *args, **kwargs: rpc(self.database, method, *args, **kwargs)

        class ClientProxy:
            def __init__(self, tracker):
                self.tracker = tracker

            def import_csv(self, *args, **kwargs):
                return rpc(self.tracker.database, "__client_import__", *args, **kwargs)

            def submit(self, *args, **kwargs):
                return rpc(self.tracker.database, "__client_submit__", *args, **kwargs)

        try:
            sandbox.start(files)
            result = _grader().grade(
                task_definition.requirements,
                types.SimpleNamespace(
                    IssueTracker=TrackerProxy, Conflict=Conflict, InvalidCursor=InvalidCursor
                ),
                types.SimpleNamespace(ImportClient=ClientProxy),
                task_definition.variant,
            )
        finally:
            retirement = sandbox.close()
        if boundary_failures:
            result = {
                **result,
                "passed": False,
                "cause": "candidate_rpc_boundary_failed",
                "boundary_failures": boundary_failures,
            }
        return {
            **result,
            "mode": "linux_candidate_rpc_external_grader",
            "tree_digest": verified_digest,
            "grader_digest": task_definition.as_dict()["grader_sha256"],
            "environment_digest": self.environment_digest,
            "observations": observations,
            "retirement": retirement,
            "limitations": [
                "bounded synchronous RPC workload; no hostile-kernel escape certification",
                "reopens database per operation; in-process lifetime differs from application server",
            ],
        }
