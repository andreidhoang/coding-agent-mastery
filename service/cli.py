"""Local reference CLI; no implicit provider, cloud, or GPU execution."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run the scripted end-to-end reference")
    demo.add_argument("--output", default=None)
    demo.add_argument("--database-url", default=None)
    demo.add_argument(
        "--sandbox-image", default=None, help="pinned local Docker image enables external Linux verifier"
    )
    demo.add_argument("--workers", type=int, choices=(1, 2, 4), default=2)
    demo.add_argument("--workload", default=None)
    commands.add_parser("workloads", help="Inspect frozen synthetic task inventory")
    commands.add_parser("doctor", help="Inspect dependencies and hardware without starting services")
    from .repair_cli import add_commands

    add_commands(commands)
    from .qualification_cli import add_commands as add_qualification_commands

    add_qualification_commands(commands)
    args = parser.parse_args(argv)
    if args.command.startswith("qualification-"):
        from .qualification_cli import execute

        print(json.dumps(execute(args), indent=2))
        return
    if args.command.startswith("repair-"):
        from .repair_cli import execute

        print(json.dumps(execute(args), indent=2))
        return
    if args.command == "doctor":
        import importlib.metadata
        import platform

        packages = {}
        for name in ("sqlalchemy", "fastapi", "httpx", "temporalio", "psycopg", "torch"):
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = None
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "packages": packages,
                    "live_inference": "disabled",
                    "human_mastery": "not assessed",
                },
                indent=2,
            )
        )
        return
    from workloads import list_tasks, validate_assets

    if args.command == "workloads":
        print(
            json.dumps(
                {"integrity": validate_assets(), "tasks": [t.as_dict() for t in list_tasks()]}, indent=2
            )
        )
        return
    from .artifacts import LocalArtifacts
    from .engine import ReferenceEngine
    from .reporting import write_report
    from .storage import RuntimeStore

    output = Path(args.output or (".runtime/demo-" + uuid.uuid4().hex[:12])).resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts = LocalArtifacts(output / "artifacts")
    store = RuntimeStore(args.database_url or "sqlite:///" + str(output / "authority.sqlite"), artifacts)
    engine = ReferenceEngine(store, artifacts, output / "workspaces", args.sandbox_image)
    try:
        workload = args.workload or list_tasks(tier="T3")[0].task_id
        task = engine.submit_fixture(workload, key="demo-" + uuid.uuid4().hex, workers=args.workers)
        snapshot = engine.run_task("demo", task["task_id"])
        events = store.events("demo", task["task_id"], limit=1000)["events"]
        report = write_report(output, snapshot, events)
        print(
            json.dumps(
                {
                    "task_id": task["task_id"],
                    "state": report["execution_state"],
                    "review": report["review_state"],
                    "budget": report["budget"],
                    "trace": str(output / "trace.html"),
                    "output": str(output),
                    "evidence": report["evidence_kind"],
                },
                indent=2,
            )
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
