"""Explicit local repair commands; preparation/reporting never purchase inference."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .artifacts import LocalArtifacts
from .protocol import strict_json
from .repair import RepairEngine, committed_repair_events
from .repair_provider import ProviderApproval
from .repair_reporting import write_repair_report
from .repair_verification import PythonFunctionRecipe, PythonFunctionVerifier
from .repositories import freeze_repository
from .storage import RuntimeStore


def add_commands(commands):
    demo = commands.add_parser("repair-demo", help="Native mock provider plus real isolated function checks")
    demo.add_argument("--output", required=True)
    demo.add_argument("--sandbox-image", required=True, help="already present immutable local Linux Python image")
    demo.add_argument("--pause-after-turn", type=int, default=None)
    demo.add_argument("--resume", action="store_true")
    prepare = commands.add_parser("repair-prepare", help="Freeze an explicitly supported local repository task")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--repository", required=True)
    prepare.add_argument("--repo-id", required=True)
    prepare.add_argument("--source", action="append", required=True)
    prepare.add_argument("--writable", action="append", required=True)
    prepare.add_argument("--recipe", required=True)
    prepare.add_argument("--provider-approval", required=True)
    prepare.add_argument("--issue-file", required=True)
    prepare.add_argument("--sandbox-image", required=True)
    prepare.add_argument("--budget-micro-usd", type=int, required=True)
    prepare.add_argument("--execution-deadline", type=float, required=True, help="absolute Unix seconds")
    prepare.add_argument("--review-deadline", type=float, required=True, help="absolute Unix seconds")
    prepare.add_argument("--key", default="repair-v1")
    prepare.add_argument("--tenant", default="repair")
    prepare.add_argument("--expected-commit", default=None)
    prepare.add_argument("--max-turns", type=int, default=12)
    prepare.add_argument("--max-worker-tests", type=int, default=4)
    run = commands.add_parser("repair-run", help="Run/resume a frozen repair with explicit provider enablement")
    run.add_argument("--output", required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--pause-after-turn", type=int, default=None)
    run.add_argument("--enable-network", action="store_true")
    report = commands.add_parser("repair-report", help="Rebuild a saved repair report without inference")
    report.add_argument("--output", required=True)


def _json_file(path, bound=1048576):
    with Path(path).open("rb") as stream:
        data = stream.read(bound + 1)
    if len(data) > bound:
        raise ValueError("configuration file exceeds bound")
    return strict_json(data.decode("utf-8"), max_bytes=bound)


def _resources(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts = LocalArtifacts(output / "artifacts")
    private = LocalArtifacts(output / "control-inputs")
    store = RuntimeStore("sqlite:///" + str(output / "authority.sqlite"), artifacts)
    return output, artifacts, private, store


def _identity(output):
    info = _json_file(output / "repair-task.json", 65536)
    if (not isinstance(info, dict) or set(info) != {"schema", "tenant", "task_id", "image"}
            or type(info["schema"]) is not int or info["schema"] != 1):
        raise ValueError("invalid saved repair identity")
    return info


def _saved_config(private, store, info):
    task = store.get_task(info["tenant"], info["task_id"])
    inputs = private.get_json(info["tenant"], info["task_id"], task["contract"]["repair_spec"]["input_digest"])
    return PythonFunctionRecipe.from_dict(inputs["recipe"]), ProviderApproval.from_dict(inputs["provider"])


def execute(args):
    if args.command == "repair-demo":
        from .repair_demo import run_demo

        return run_demo(args.output, args.sandbox_image, pause_after_turn=args.pause_after_turn, resume=args.resume)
    output, artifacts, private, store = _resources(args.output)
    try:
        if args.command == "repair-prepare":
            if (output / "repair-task.json").exists():
                raise ValueError("output already binds a task; use its saved run or a fresh output directory")
            repository = freeze_repository(args.repository, args.repo_id, args.source, args.writable,
                                           expected_commit=args.expected_commit)
            recipe = PythonFunctionRecipe.from_dict(_json_file(args.recipe))
            approval = ProviderApproval.from_dict(_json_file(args.provider_approval))
            with Path(args.issue_file).open("rb") as stream:
                issue = stream.read(32769)
            if len(issue) > 32768:
                raise ValueError("issue file byte bound exceeded")
            verifier = PythonFunctionVerifier(args.sandbox_image, recipe=recipe)
            engine = RepairEngine(store, artifacts, output / "workspaces", verifier, private_inputs=private)
            task = engine.submit(
                repository, recipe, approval, issue.decode(), tenant=args.tenant, key=args.key,
                budget_units=args.budget_micro_usd, execution_deadline=args.execution_deadline,
                review_deadline=args.review_deadline, max_turns=args.max_turns,
                max_worker_tests=args.max_worker_tests,
            )
            info = {"schema": 1, "tenant": args.tenant, "task_id": task["task_id"], "image": verifier.image}
            (output / "repair-task.json").write_text(json.dumps(info, indent=2) + "\n")
            return {**info, "prepared": True, "provider_network": "disabled; no inference performed"}
        info = _identity(output)
        if args.command == "repair-run":
            recipe, approval = _saved_config(private, store, info)
            if not args.enable_network:
                raise PermissionError("repair-run requires explicit --enable-network and approved account/spend inputs")
            key = os.environ.get("NEBIUS_API_KEY")
            if not key:
                raise PermissionError("server-held NEBIUS_API_KEY is not configured")
            model = approval.build_adapter(key, enable_network=True)
            verifier = PythonFunctionVerifier(info["image"], recipe=recipe)
            engine = RepairEngine(store, artifacts, output / "workspaces", verifier, private_inputs=private)
            try:
                snapshot = engine.run_task(info["tenant"], info["task_id"], model, resume=args.resume,
                                           pause_after_turn=args.pause_after_turn)
            finally:
                model.client.close()
        else:
            snapshot = store.snapshot(info["tenant"], info["task_id"])
            snapshot["evidence_kind"] = "saved_supported_repair; inspect requests; live capability is not inferred"
            snapshot["repair_scope"] = "supported stateless Python functions; human review remains separate"
        events = committed_repair_events(store, info["tenant"], info["task_id"], snapshot)
        report = write_repair_report(output, snapshot, events, artifacts=artifacts)
        return {"task_id": info["task_id"], "state": snapshot["task"]["execution_state"],
                "paused": snapshot.get("paused", False), "verified": report["verified"],
                "report": str(output / "repair.html")}
    finally:
        store.close()
