"""Standalone installed-package acceptance; native HTTP is always mocked.

Run with a fresh virtualenv's Python -I from outside every source checkout.
This file uses installed product APIs, never repository tests or path injection.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import sysconfig


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def deny_network():
    original = socket.socket.connect

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError("acceptance forbids external network sockets")
        return original(sock, address)

    socket.socket.connect = connect
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("acceptance forbids external network sockets"))


CLI_GUARD = """import socket,sys,json,hashlib
from pathlib import Path
original=socket.socket.connect
def connect(sock,address):
    if sock.family in (socket.AF_INET,socket.AF_INET6):
        raise RuntimeError('acceptance forbids external network sockets')
    return original(sock,address)
socket.socket.connect=connect
socket.create_connection=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('network forbidden'))
from service.cli import main
main(sys.argv[2:])
origins={}
for name,module in sorted(sys.modules.items()):
    if name.split('.')[0] in {'service','workloads','evals','compute'}:
        path=Path(module.__file__).resolve()
        origins[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
Path(sys.argv[1]).write_text(json.dumps(origins,indent=2)+'\\n')
"""

# Only the test-owned configured service child uses this observational wrapper.
# It executes the installed product entrypoint with the unchanged worker arguments.
WORKER_GUARD = CLI_GUARD.replace("from service.cli import main", "from service.offline_server import main").replace(
    "main(sys.argv[2:])", "exit_code=main(sys.argv[2:])").replace(
    "Path(sys.argv[1]).write_text(json.dumps(origins,indent=2)+'\\n')",
    "Path(sys.argv[1]).write_text(json.dumps({'pid':__import__('os').getpid(),'executable':sys.executable,"
    "'origins':origins},indent=2)+'\\n')\nraise SystemExit(exit_code)")


def command(argv, output, label, *, timeout=240):
    result = subprocess.run(argv, cwd=output, text=True, capture_output=True, timeout=timeout)
    (output / (label + ".stdout.txt")).write_text(result.stdout, encoding="utf-8")
    (output / (label + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
    require(result.returncode == 0, f"{label} failed; inspect preserved stderr")
    return result.stdout


def cli(output, label, *args):
    return json.loads(command([sys.executable, "-I", "-c", CLI_GUARD,
                               str(output / (label + ".origins.json")), *args], output, label))


def manifest_files(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    files = manifest["files"]
    if isinstance(files, list):
        require(len({row["path"] for row in files}) == len(files), "duplicate manifest paths")
        files = {row["path"]: row for row in files}
    require(isinstance(files, dict) and files, "source manifest has no files")
    return files


def validate_origins(records, files, forbidden):
    roots = {Path(sysconfig.get_path(k)).resolve() for k in ("purelib", "platlib")}
    for name, record in records.items():
        path = Path(record["path"]).resolve()
        require(any(path.is_relative_to(root) for root in roots), f"noninstalled product origin: {name}")
        require(not any(path.is_relative_to(root) for root in forbidden), f"forbidden product origin: {name}")
        relative = path.relative_to(next(root for root in roots if path.is_relative_to(root))).as_posix()
        require(relative in files, f"loaded module absent from source manifest: {relative}")
        observed = sha(path.read_bytes())
        expected = files[relative]
        require(observed == record["sha256"] ==
                (expected if isinstance(expected, str) else expected["sha256"]),
                f"installed module differs from frozen source: {relative}")
    require(records, "no product origins recorded")
    return records


def origins(files, forbidden):
    records = {}
    for name, module in sorted(sys.modules.items()):
        if name.split(".")[0] not in {"service", "workloads", "evals", "compute"}:
            continue
        location = getattr(module, "__file__", None)
        require(location is not None, f"product module lacks origin: {name}")
        path = Path(location).resolve()
        observed = sha(path.read_bytes())
        records[name] = {"path": str(path), "sha256": observed}
    return validate_origins(records, files, forbidden)


def installed_assets(files):
    from workloads.registry import ROOT, validate_assets
    from service.repair_demo import demo_inputs

    assets = []
    for relative, expected in sorted(files.items()):
        if not relative.startswith("workloads/"):
            continue
        path = ROOT.parent / relative
        require(path.is_file() and not path.is_symlink(), f"missing installed asset: {relative}")
        data = path.read_bytes()
        require(sha(data) == (expected if isinstance(expected, str) else expected["sha256"]),
                f"installed asset differs from frozen source: {relative}")
        assets.append({"path": relative, "sha256": sha(data), "size": len(data)})
    repository, recipe, approval, _ = demo_inputs()
    require(list(repository.files) == ["slug.py"], "repair intake must contain only declared source")
    require(approval.as_dict()["evidence"]["kind"] == "mock", "repair fixture provider must be mocked")
    return {"registry": validate_assets(), "assets": assets,
            "repair_repository_digest": repository.manifest_digest, "recipe_digest": recipe.grader_digest}


def repair_checks(output, image):
    from service.artifacts import LocalArtifacts
    from service.execution import tree_digest
    from service.repair_demo import demo_inputs
    from service.repair_reporting import write_repair_report

    full_path, resumed_path = output / "repair-full", output / "repair-resumed"
    full = cli(output, "repair-full", "repair-demo", "--output", str(full_path), "--sandbox-image", image)
    paused = cli(output, "repair-paused", "repair-demo", "--output", str(resumed_path),
                 "--sandbox-image", image, "--pause-after-turn", "2")
    pause_snapshot = json.loads((resumed_path / "snapshot.json").read_text())
    require(paused["paused"] and paused["mock_requests_this_process"] == 2, "pause boundary differs")
    require(all(s["status"] == "retired" for s in pause_snapshot["sandboxes"]), "pause retains environment")
    resumed = cli(output, "repair-resumed", "repair-demo", "--output", str(resumed_path),
                  "--sandbox-image", image, "--resume")
    require(full["mock_requests_this_process"] == 5, "uninterrupted demo changed request count")
    require(resumed["mock_requests_this_process"] == 3, "resume repeated an earlier model request")
    require(paused["task_id"] == resumed["task_id"], "resume created a different task")
    resumed_snapshot = json.loads((resumed_path / "snapshot.json").read_text())
    resumed_artifacts = LocalArtifacts(resumed_path / "artifacts")
    pause_checkpoint = max(pause_snapshot["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    pause_payload = resumed_artifacts.get_json(pause_snapshot["task"]["tenant_id"], paused["task_id"],
                                               pause_checkpoint["manifest"]["artifact_ref"]["digest"])
    resumed_attempt = next(a for a in resumed_snapshot["attempts"] if a["node_epoch"] == 2)
    resumed_action = f"model-{resumed_attempt['attempt_id']}-{pause_checkpoint['manifest']['next_turn']}"
    resumed_model = next(d for d in resumed_snapshot["dispatches"] if d["kind"] == "model.nebius"
                         and d["action_id"] == resumed_action)
    resumed_request = resumed_artifacts.get_json(pause_snapshot["task"]["tenant_id"], paused["task_id"],
                                                 resumed_model["input_digest"])
    require(resumed_request["payload"]["messages"][1:] == pause_payload["messages"],
            "fresh process did not preserve exact native checkpoint history")
    repository, _, _, _ = demo_inputs()
    summaries = []
    for directory in (full_path, resumed_path):
        snapshot = json.loads((directory / "snapshot.json").read_text())
        report = json.loads((directory / "repair.json").read_text())
        require(report["verified"] and report["execution_state"] == "review_eligible", "repair not verified")
        require(report["review_state"] == "pending", "mock repair inferred human acceptance")
        require(snapshot["task"]["contract"]["capabilities"] ==
                ["read_file", "search", "replace_text", "run_tests", "finish"], "repair capability drift")
        require(all(s["status"] == "retired" for s in snapshot["sandboxes"]), "repair retains environment")
        models = [d for d in snapshot["dispatches"] if d["kind"] == "model.nebius"]
        require(len(models) == 5, "repair ledger must record five native requests")
        require(len([d for d in snapshot["dispatches"] if d["kind"] == "run_tests"]) == 2,
                "worker test allowance lost across restart")
        require(len(snapshot["verifications"]) == 1, "final verification receipt missing or duplicated")
        require(report["budget"]["spent"] == report["budget"]["reserved"] == 0, "mock billing differs")
        candidate = next(c for c in snapshot["candidates"] if c["candidate_id"] == snapshot["task"]["head_candidate_id"])
        require(report["candidate"]["tree_digest"] == candidate["tree_digest"], "report candidate identity differs")
        patch = (directory / "change.patch").read_bytes()
        require(patch == report["candidate"]["patch"].encode(), "download is not exact stored patch")
        patch_root = output / (directory.name + "-patch-application")
        patch_root.mkdir()
        for name, text in repository.files.items():
            target = patch_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode())
        applied = subprocess.run(["git", "apply", str(directory / "change.patch")],
                                 cwd=patch_root, capture_output=True, text=True, timeout=30)
        write_json(output / (directory.name + "-git-apply.json"),
                   {"returncode": applied.returncode, "stdout": applied.stdout, "stderr": applied.stderr})
        require(applied.returncode == 0, "independent patch application failed")
        reconstructed = {name: (patch_root / name).read_bytes().decode() for name in repository.files}
        require(reconstructed == candidate["manifest"]["files"], "patch does not reconstruct exact candidate bytes")
        require(tree_digest(reconstructed) == candidate["tree_digest"], "independent tree identity differs")
        replay = cli(output, directory.name + "-replay", "repair-report", "--output", str(directory))
        after = json.loads((directory / "snapshot.json").read_text())
        require(after["dispatches"] == snapshot["dispatches"], "report replay created or altered dispatches")
        require(replay["verified"], "report replay lost exact current-head pass")
        damaged = copy.deepcopy(snapshot)
        damaged["candidates"][next(i for i, c in enumerate(damaged["candidates"])
                                   if c["candidate_id"] == candidate["candidate_id"])]["tree_digest"] = "f" * 64
        negative_dir = output / (directory.name + "-stale-report-control")
        negative_dir.mkdir()
        negative = write_repair_report(negative_dir, damaged, [], artifacts=LocalArtifacts(directory / "artifacts"))
        require(not negative["verified"], "damaged snapshot falsely verifies")
        summaries.append({"task_id": report["task_id"], "candidate_digest": candidate["tree_digest"],
                          "patch_sha256": sha(patch), "requests": len(models), "slots_retired": True,
                          "epochs": sorted(a["node_epoch"] for a in snapshot["attempts"]),
                          "native_history_sha256": [d["input_digest"] for d in models],
                          "dispatch_count_before_replay": len(snapshot["dispatches"]),
                          "dispatch_count_after_replay": len(after["dispatches"]), "stale_report_denied": True})
    require(summaries[1]["epochs"] == [1, 2], "clean restart did not advance owner epoch")
    require(summaries[0]["candidate_digest"] == summaries[1]["candidate_digest"], "restart candidate changed")
    require(summaries[0]["patch_sha256"] == summaries[1]["patch_sha256"], "restart exact patch changed")
    return {"uninterrupted": summaries[0], "clean_process_restart": summaries[1]}


def qualification_case(directory, image):
    """Installed-only CLI/API qualification over an exact unstarted prepared repair."""
    import os
    import sqlite3
    import time
    import httpx
    from service.artifacts import LocalArtifacts
    from service.billing import ProviderEnvelope
    from service.repair_demo import demo_inputs
    from service import qualification

    directory.mkdir()
    repository, recipe, approval, _ = demo_inputs()
    source = directory / "repository"
    source.mkdir()
    for name, text in repository.files.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    provider = approval.as_dict()
    provider["rate_snapshot"].update(rate_id="installed:synthetic-positive-qualification",
                                      input_per_million=1000, output_per_million=2000)
    issue = "INSTALLED_PRIVATE_QUALIFICATION_ISSUE_17cb"
    private_case = "INSTALLED_PRIVATE_QUALIFICATION_CASE_f329"
    recipe_data = recipe.as_dict()
    recipe_data["final_cases"].append({"id": private_case, "function": "normalize_slug",
        "args": [private_case], "kwargs": {}, "expect": {"value": "installed-private-qualification-case-f329"}})
    write_json(directory / "provider.json", provider)
    write_json(directory / "recipe.json", recipe_data)
    (directory / "issue.txt").write_text(issue)
    prepared = directory / "prepared-repair"
    now = time.time()
    intake = cli(directory, "qualification-repair-prepare", "repair-prepare", "--output", str(prepared),
        "--repository", str(source), "--repo-id", "installed-qualification-repair", "--source", "slug.py",
        "--writable", "slug.py", "--recipe", str(directory / "recipe.json"),
        "--provider-approval", str(directory / "provider.json"), "--issue-file", str(directory / "issue.txt"),
        "--sandbox-image", image, "--budget-micro-usd", "10000", "--execution-deadline", str(now + 7200),
        "--review-deadline", str(now + 14400))
    require(intake["prepared"], "qualification upstream repair not prepared")

    def tree(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    upstream = tree(prepared)
    target = directory / "qualification"
    cli(directory, "qualification-prepare", "qualification-prepare", "--output", str(target),
        "--repair-output", str(prepared), "--execution-deadline", str(now + 600),
        "--review-deadline", str(now + 1200))
    manifest = json.loads((target / "manifest.json").read_bytes())
    require(manifest["provider_approval"] == provider, "qualification relabeled approval")
    require(manifest["budget_units"] == 2 * ProviderEnvelope(provider["rate_snapshot"], provider["model"]).bound_units,
            "qualification budget not two native envelope bounds")
    os.environ["NEBIUS_API_KEY"] = "INSTALLED_AMBIENT_NOT_CREDENTIAL_23a1"
    report = cli(directory, "qualification-run", "qualification-run", "--output", str(target))
    require(report["passed"] and report["evidence_kind"] == "offline_mock", "offline qualification failed")
    for flag in ("live_observed", "g1_passed", "g2_passed", "execution_authority"):
        require(report[flag] is False, "qualification invented live/dispatch authority")
    completed = tree(target)
    require(cli(directory, "qualification-report", "qualification-report", "--output", str(target)) == report,
            "report changed saved offline evidence")
    require(cli(directory, "qualification-run-repeat", "qualification-run", "--output", str(target)) == report,
            "duplicate qualification changed report")
    require(tree(target) == completed, "duplicate/report rewrote evidence")
    handoff = cli(directory, "qualification-handoff", "qualification-handoff", "--output", str(target),
                  "--repair-output", str(prepared))
    require(handoff["execution_authority"] is False, "handoff grants execution")
    handoff_bytes = (target / "handoff.json").read_bytes()
    require(cli(directory, "qualification-handoff-repeat", "qualification-handoff", "--output", str(target),
                "--repair-output", str(prepared)) == handoff, "handoff identity changed")
    require((target / "handoff.json").read_bytes() == handoff_bytes, "handoff bytes changed")
    require(tree(prepared) == upstream, "qualification modified prepared repair")
    require(all(secret.encode() not in b"\n".join(tree(target).values()) for secret in
                (issue, private_case, os.environ["NEBIUS_API_KEY"])), "qualification leaked private inputs/key")
    with sqlite3.connect(f"file:{target / 'authority.sqlite'}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        dispatches = [json.loads(d["data"]) for d in db.execute("select * from dispatches")]
    models = sorted((d for d in dispatches if d["kind"] == "model.nebius"),
                    key=lambda d: int(d["action_id"].rsplit("-", 1)[1]))
    require(len(models) == 2 and all(d["billing_state"] == "settled" and d["actual_units"] > 0 for d in models),
            "qualification lacks exactly two nonzero settled native requests")
    artifacts = LocalArtifacts(target / "artifacts")
    requests, raw = [], []
    for dispatch in models:
        requests.append(artifacts.get_json(dispatch["tenant_id"], dispatch["task_id"], dispatch["input_digest"]))
        ref = json.loads(dispatch["result_ref"]) if isinstance(dispatch["result_ref"], str) else dispatch["result_ref"]
        body = artifacts.get(ref["tenant_id"], ref["task_id"], ref["digest"])
        require(len(body) == ref["size"], "raw response size mismatch")
        raw.append(json.loads(body))
    first = raw[0]["choices"][0]["message"]
    require(first in requests[1]["payload"]["messages"], "opaque native assistant lost")
    require(any(k not in {"role", "content", "tool_calls"} for k in first), "opaque fixture field missing")
    call_id = first["tool_calls"][0]["id"]
    tool = next(m for m in requests[1]["payload"]["messages"] if m.get("tool_call_id") == call_id)
    read = json.loads(tool["content"])
    require(sha(read["value"]["text"].encode()) == sha(manifest["fixture"]["text"].encode()), "broker fixture linkage lost")

    negative = directory / "qualification-corrupt"
    __import__("shutil").copytree(target, negative)
    ref = json.loads(models[0]["result_ref"]) if isinstance(models[0]["result_ref"], str) else models[0]["result_ref"]
    (negative / "artifacts" / ref["tenant_id"] / ref["task_id"] / ref["digest"]).write_bytes(b"corrupt receipt")
    try:
        qualification.create_qualification_handoff(negative, prepared)
    except (ValueError, RuntimeError, FileNotFoundError):
        pass
    else:
        raise AssertionError("corrupt receipt accepted for handoff")

    forged = directory / "qualification-canonical-forgery"
    __import__("shutil").copytree(target, forged)
    changed = json.loads((forged / "manifest.json").read_bytes())
    changed["execution_deadline"] += 1
    frozen_type = qualification.QualificationManifest.from_dict(changed)
    from service.artifacts import canonical_bytes
    (forged / "manifest.json").write_bytes(canonical_bytes(changed))
    (forged / "started.json").write_bytes(canonical_bytes({"schema": 1, "manifest_digest": frozen_type.digest}))
    index = json.loads((forged / "report.json").read_bytes())
    forged_artifacts = LocalArtifacts(forged / "artifacts")
    original_ref = index["report_ref"]
    bundle = forged_artifacts.get_json(original_ref["tenant_id"], original_ref["task_id"], original_ref["digest"])
    bundle["manifest_digest"] = frozen_type.digest
    index["manifest_digest"] = frozen_type.digest
    index["report_ref"] = forged_artifacts.put_json(original_ref["tenant_id"], original_ref["task_id"], bundle)
    (forged / "report.json").write_bytes(canonical_bytes(index))
    (forged / "handoff.json").unlink()
    for inspect in (lambda: qualification.read_qualification_report(forged),
                    lambda: qualification.create_qualification_handoff(forged, prepared)):
        try:
            inspect()
        except (ValueError, RuntimeError):
            pass
        else:
            raise AssertionError("canonical manifest/report rehash rebound original durable probe")

    failed = directory / "qualification-timeout"
    qualification.prepare_qualification(failed, prepared, execution_deadline=now + 600, review_deadline=now + 1200)
    sent = []
    original = qualification._mock_transport
    def timeout_transport(approval):
        def handler(request):
            sent.append(request)
            raise httpx.ReadTimeout("installed fixture timeout", request=request)
        return handler
    qualification._mock_transport = timeout_transport
    try:
        lost = qualification.run_qualification(failed)
        require(not lost["passed"], "Unknown qualification passed")
        require(qualification.run_qualification(failed) == lost and len(sent) == 1, "Unknown qualification resent")
    finally:
        qualification._mock_transport = original
    with sqlite3.connect(f"file:{failed / 'authority.sqlite'}?mode=ro", uri=True) as db:
        rows = [json.loads(row[0]) for row in db.execute("select data from dispatches")]
        row = next(d for d in rows if d["kind"] == "model.nebius")
    require(row["effect_state"] == "unknown" and row["billing_state"] == "liability_unknown" and row["actual_units"] is None and row["bound_units"] > 0,
            "Unknown qualification liability dropped")
    return {"prepared_task_id": intake["task_id"], "manifest_sha256": sha((target / "manifest.json").read_bytes()),
            "native_requests": len(models), "synthetic_spent": sum(d["actual_units"] for d in models),
            "upstream_unchanged": True, "opaque_linkage": True, "all_four_cli_paths": True,
            "duplicate_no_resend": True, "corrupt_receipt_denied": True, "canonical_forgery_denied": True,
            "unknown_no_resend": True,
            "execution_authority": False, "live_observed": False}


MODEL = "release/synthetic-context-only"
SENTINEL = "RELEASE_OLD_TOOL_SENTINEL_3e48"
CAPABILITIES = ["read_file", "read_context_artifact", "finish"]


def context_rates():
    return {"schema": 1, "unit": "micro_usd", "rate_id": "release-context-mock", "model": MODEL,
            "input_token_bound": 100, "max_output_tokens": 100, "input_per_million": 10000,
            "output_per_million": 20000, "cache_read_per_million": 1000,
            "cache_write_per_million": 15000, "bound_evidence": "synthetic mock only",
            "max_request_bytes": 65536}


def context_config():
    return {"schema": 1, "strategy": "tool_result_offload_v1", "max_bytes": 18000,
            "min_offload_bytes": 1024, "keep_recent_tool_batches": 1, "retrieval_max_bytes": 8192}


def native_response(name=None, args=None, identity="done"):
    message = {"role": "assistant", "content": None if name else "mock completion"}
    if name:
        message["tool_calls"] = [{"id": identity, "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(args)}}]
    return {"id": identity, "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "tool_calls" if name else "stop", "message": message}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}


def expect_error(function, label, expected_type, expected_message):
    try:
        function()
    except expected_type as error:
        require(type(error) is expected_type, label + " raised a different exception subclass")
        require(expected_message in str(error), label + " failed at a different invariant: " + str(error))
        return {"control": label, "error_type": type(error).__name__, "detail": str(error)}
    raise AssertionError(label + " unexpectedly succeeded")


def context_case(directory, *, lost_response=False):
    import httpx
    from service.artifacts import LocalArtifacts, digest_json
    from service.context_retrieval import read_context_artifact
    from service.contracts import CapacityExceeded
    from service.execution import Workspace, materialize, tree_digest
    from service.harness import Harness
    from service.providers import NebiusChatCompletions
    from service.recovery import restore_checkpoint, validate_context_manifest
    from service.storage import RuntimeStore

    directory.mkdir()
    artifacts = LocalArtifacts(directory / "artifacts")
    url = "sqlite:///" + str(directory / "runtime.db")
    store = RuntimeStore(url, artifacts)
    files = {"earlier.txt": SENTINEL + "q" * 10000, "latest.txt": "r" * 10000}
    contract = {"repo_id": "release-context-fixture", "base_revision": tree_digest(files),
                "requirements": ["Read two files; retrieve earlier bytes; propose completion."],
                "model": MODEL, "capabilities": CAPABILITIES[:], "rate_snapshot": context_rates()}
    task = store.submit("release-context", "release-context-case", contract)
    tenant, task_id = task["tenant_id"], task["task_id"]
    store.set_graph(tenant, task_id, task["generation"], [{"node_id": "reader"}])
    owner = store.claim(tenant, task_id, "reader", "initial", 100, 120)["owner"]
    materialize(directory / "workspace", files)
    workspace = Workspace(directory / "workspace", list(files))
    observations = []

    def observe(request, controller, selected_owner):
        payload = json.loads(request.content)
        snapshot = controller.snapshot(tenant, task_id)
        dispatch = next(d for d in snapshot["dispatches"] if d["attempt_id"] == selected_owner["attempt_id"]
                        and d["kind"] == "model.nebius" and d["effect_state"] == "in_flight")
        acceptance = dispatch["context_acceptance"]
        manifest = acceptance["manifest"]
        accepted = artifacts.get_json(tenant, task_id, manifest["request_ref"]["digest"])
        observed_record = {**accepted, "payload": payload}
        observed_digest = digest_json(observed_record)
        require(observed_digest == digest_json(accepted) == manifest["request_digest"] == dispatch["input_digest"],
                "canonical request wrapper identity differs")
        require(digest_json(manifest) == acceptance["projection_id"], "projection acceptance identity differs")
        ordinal = len(observations)
        write_json(directory / f"request-{ordinal}.json", payload)
        (directory / f"request-{ordinal}.wire.json").write_bytes(request.content)
        write_json(directory / f"request-{ordinal}.accepted.json", accepted)
        write_json(directory / f"request-{ordinal}.dispatch.json", dispatch)
        observations.append({"dispatch": copy.deepcopy(dispatch), "payload": payload,
                             "wire_sha256": sha(request.content), "canonical_wrapper_sha256": digest_json(accepted),
                             "observed_canonical_wrapper_sha256": observed_digest})
        return manifest

    def handler(request):
        manifest = observe(request, store, owner)
        turn = len(observations)
        if turn == 1:
            response = native_response("read_file", {"path": "earlier.txt"}, "earlier")
            response["choices"][0]["message"]["reasoning_content"] = "opaque native mock field"
        elif turn == 2:
            response = native_response("read_file", {"path": "latest.txt"}, "latest")
        else:
            require(SENTINEL not in json.dumps(observations[-1]["payload"]), "old sentinel remained on wire")
            require(manifest["offload_refs"], "old tool body was not offloaded")
            if lost_response:
                raise httpx.ReadTimeout("synthetic loss after accepted send")
            response = native_response("read_context_artifact", {
                "digest": manifest["offload_refs"][0]["digest"], "offset": 0, "limit": 1024}, "retrieve")
        return httpx.Response(200, json=response)

    model = NebiusChatCompletions("mock-no-live-key", MODEL, enable_network=True,
                                 client=httpx.Client(transport=httpx.MockTransport(handler)))
    harness = Harness(store, artifacts, provider_envelopes={MODEL: context_rates()}, context_config=context_config())
    try:
        if lost_response:
            expect_error(lambda: harness.run(owner, task["contract"], workspace, model), "lost_response",
                         httpx.ReadTimeout, "synthetic loss after accepted send")
            result = None
        else:
            result = harness.run(owner, task["contract"], workspace, model, pause_after_turn=3)
    finally:
        model.client.close()
    snapshot = store.snapshot(tenant, task_id)
    checkpoint = max(snapshot["checkpoints"], key=lambda c: c["manifest"]["next_turn"])
    write_json(directory / "snapshot-before-recovery.json", snapshot)
    require(snapshot["task"]["contract"]["capabilities"] == CAPABILITIES, "context changed capabilities")
    require(len(observations) == 3, "context scenario request count differs")
    controls = []
    if lost_response:
        last = next(d for d in snapshot["dispatches"]
                    if d["dispatch_id"] == observations[-1]["dispatch"]["dispatch_id"])
        require(last["effect_state"] == "unknown" and last["billing_state"] != "settled", "loss not retained Unknown")
        require(type(last["bound_units"]) is int and last["bound_units"] > 0,
                "Unknown dispatch lacks a positive unsettled bound")
        require(snapshot["budget"]["reserved"] >= last["bound_units"], "Unknown liability was not reserved")
        dispatch_ids = [d["dispatch_id"] for d in snapshot["dispatches"]]

        def same_dispatches(state):
            require([d["dispatch_id"] for d in state["dispatches"]] == dispatch_ids,
                    "Unknown recovery changed dispatch identities/count")

        store.close()
        controller = RuntimeStore(url, artifacts)
        try:
            before_denial = controller.snapshot(tenant, task_id)
            controls.append(expect_error(lambda: restore_checkpoint(controller, artifacts, tenant, task_id,
                                                                    checkpoint["checkpoint_id"]), "unknown_restore",
                                         ValueError, "post-checkpoint effects require explicit reconciliation; cannot rewind"))
            after_restore_denial = controller.snapshot(tenant, task_id)
            require(after_restore_denial == before_denial, "denied restore mutated runtime state")
            same_dispatches(after_restore_denial)
            controls.append(expect_error(lambda: controller.claim(tenant, task_id, "reader", "unsafe-retry", 90, 120),
                                         "unknown_replacement", CapacityExceeded,
                                         "previous environment retirement unconfirmed"))
            after_claim_denial = controller.snapshot(tenant, task_id)
            require(after_claim_denial == before_denial, "denied replacement mutated runtime state")
            same_dispatches(after_claim_denial)
            spent = snapshot["budget"]["spent"]
            controller.finish_dispatch(tenant, last["dispatch_id"], "release-late-cost", "unknown", 1)
            once_settled = controller.snapshot(tenant, task_id)
            same_dispatches(once_settled)
            controller.finish_dispatch(tenant, last["dispatch_id"], "release-late-cost", "unknown", 1)
            settled = controller.snapshot(tenant, task_id)
            same_dispatches(settled)
            require(settled == once_settled, "duplicate late settlement mutated runtime state")
            require(settled["budget"]["spent"] == spent + 1, "late cost settlement not idempotent")
            require(settled["budget"]["reserved"] == snapshot["budget"]["reserved"] - last["bound_units"],
                    "late settlement did not release exactly the dispatch liability")
            late = next(d for d in settled["dispatches"] if d["dispatch_id"] == last["dispatch_id"])
            require(late["effect_state"] == "unknown" and late["billing_state"] == "settled",
                    "late cost invented effect certainty or failed billing settlement")
            controls.append(expect_error(lambda: restore_checkpoint(controller, artifacts, tenant, task_id,
                                                                    checkpoint["checkpoint_id"]), "settled_unknown_restore",
                                         ValueError, "post-checkpoint effects require explicit reconciliation; cannot rewind"))
            after_settled_denial = controller.snapshot(tenant, task_id)
            require(after_settled_denial == settled, "settled Unknown restore mutated runtime state")
            same_dispatches(after_settled_denial)
            require(len(observations) == 3, "uncertainty caused a resend")
            write_json(directory / "snapshot-after-late-settlement.json", settled)
            write_json(directory / "controls.json", controls)
            return {"mock_requests": 3, "effect_state": late["effect_state"], "cost_delta": 1,
                    "dispatch_ids_before_after": dispatch_ids, "dispatch_count": len(dispatch_ids),
                    "unsettled_dispatch_bound_before": last["bound_units"],
                    "reserved_before": snapshot["budget"]["reserved"],
                    "reserved_after_settlement": settled["budget"]["reserved"],
                    "restore_and_replacement_denied": True, "controls": controls}
        finally:
            controller.close()
    require(result["status"] == "paused" and SENTINEL in json.dumps(result["messages"]), "raw history lost")
    require(result["messages"][1]["reasoning_content"] == "opaque native mock field", "native field lost")
    acceptance = observations[-1]["dispatch"]["context_acceptance"]
    manifest = acceptance["manifest"]
    raw = artifacts.get_json(tenant, task_id, manifest["raw_history_ref"]["digest"])
    require(SENTINEL in json.dumps(raw), "accepted raw source lost sentinel")
    retrieval = next(d for d in snapshot["dispatches"] if d["kind"] == "read_context_artifact")
    receipt = artifacts.get_json(tenant, task_id, retrieval["result_ref"]["digest"])
    expected = artifacts.get(tenant, task_id, manifest["offload_refs"][0]["digest"])[:1024]
    require(base64.b64decode(receipt["value"]["bytes_base64"], validate=True) == expected, "retrieval bytes differ")
    require(SENTINEL.encode() in expected and retrieval["bound_units"] == 0, "retrieval control/zero bound differs")
    require(receipt["context_provenance"]["projection_id"] == acceptance["projection_id"], "retrieval provenance differs")
    write_json(directory / "retrieval-receipt.json", receipt)
    unrelated = artifacts.put(tenant, task_id, b"unrelated same task bytes")
    controls.append(expect_error(lambda: read_context_artifact(
        artifacts, tenant, task_id, manifest["offload_refs"],
        {"digest": unrelated["digest"], "offset": 0, "limit": 8}), "unrelated_retrieval",
        PermissionError, "digest is not authorized by current projection"))
    require(store.snapshot(tenant, task_id) == snapshot, "nondispatch retrieval probe mutated ledger")
    for fault in ("scope", "raw_alias"):
        tampered = copy.deepcopy(manifest)
        if fault == "scope":
            tampered["raw_history_ref"]["task_id"] = "another-task"
        else:
            tampered["raw_history_ref"] = tampered["projection_ref"]
        invariant = "context artifact outside task scope" if fault == "scope" else "invalid closed raw history"
        controls.append(expect_error(lambda: validate_context_manifest(artifacts, tenant, task_id, tampered),
                                     fault, ValueError, invariant))
    attempt = next(a for a in snapshot["attempts"] if a["attempt_id"] == owner["attempt_id"])
    store.retire_sandbox(tenant, attempt["sandbox_id"], {"exit_observed": True, "supervisor": "release-trusted-local-mock"})
    store.close()
    controller = RuntimeStore(url, artifacts)
    try:
        before = controller.snapshot(tenant, task_id)
        restored = restore_checkpoint(controller, artifacts, tenant, task_id, checkpoint["checkpoint_id"])
        require(controller.snapshot(tenant, task_id) == before, "restoration changed authority state")
        require("owner" not in restored and "grants none" in restored["authority"], "restore grants execution authority")
        require(restored["messages"] == result["messages"], "typed recovery changed raw history")
        write_json(directory / "typed-recovery.json", restored)
        new_owner = controller.claim(tenant, task_id, "reader", "fresh-controller", 90, 120)["owner"]
        require(new_owner["node_epoch"] == owner["node_epoch"] + 1, "fresh owner epoch did not advance")

        def resumed_handler(request):
            new_manifest = observe(request, controller, new_owner)
            require(new_manifest["binding"]["owner"] == new_owner, "accepted old owner")
            require(new_manifest["binding"]["expected_previous_projection_id"] is None, "reused old projection chain")
            require(new_manifest["source_checkpoint"] == checkpoint["checkpoint_id"], "lost checkpoint lineage")
            require(new_manifest["restored_from_projection_id"] == acceptance["projection_id"], "lost projection lineage")
            return httpx.Response(200, json=native_response())

        continuation = NebiusChatCompletions("mock-no-live-key", MODEL, enable_network=True,
                                            client=httpx.Client(transport=httpx.MockTransport(resumed_handler)))
        try:
            final = Harness(controller, artifacts, provider_envelopes={MODEL: context_rates()},
                            context_config=context_config()).run(new_owner, task["contract"], workspace,
                                                                  continuation, restored=restored)
        finally:
            continuation.client.close()
        require(final["status"] == "completion_proposed" and len(observations) == 4, "fresh owner continuation differs")
        after = controller.snapshot(tenant, task_id)
        require(after["task"]["contract"]["capabilities"] == CAPABILITIES, "resume expanded capabilities")
        new_attempt = next(a for a in after["attempts"] if a["attempt_id"] == new_owner["attempt_id"])
        controller.retire_sandbox(tenant, new_attempt["sandbox_id"],
                                  {"exit_observed": True, "supervisor": "release-trusted-local-mock"})
        after = controller.snapshot(tenant, task_id)
        require(all(s["status"] == "retired" for s in after["sandboxes"]), "clean context retains mock slots")
        write_json(directory / "snapshot-after-fresh-owner.json", after)
        write_json(directory / "final-raw-history.json", final["messages"])
        write_json(directory / "controls.json", controls)
        return {"mock_requests": 4, "canonical_request_wire_comparisons": [
            {k: v for k, v in o.items() if k != "payload" and k != "dispatch"} for o in observations],
            "old_projection_id": acceptance["projection_id"],
            "fresh_projection_id": observations[-1]["dispatch"]["context_acceptance"]["projection_id"],
            "old_epoch": owner["node_epoch"], "fresh_epoch": new_owner["node_epoch"],
            "retrieval_zero_bound": True, "raw_history_retained": True,
            "restore_grants_authority": False, "capabilities": CAPABILITIES, "controls": controls}
    finally:
        controller.close()


def skills_recovery_case(directory):
    import shutil
    import httpx
    import workloads
    from service.artifacts import LocalArtifacts, canonical_bytes, digest_json
    from service.context import default_context_config
    from service.execution import Workspace, materialize, tree_digest
    from service.harness import Harness
    from service.providers import NebiusChatCompletions
    from service.recovery import restore_checkpoint
    from service.skills import capture_skill_catalog, default_skills_config, read_catalog_snapshot
    from service.storage import RuntimeStore

    directory.mkdir()
    artifacts = LocalArtifacts(directory / "artifacts")
    url = "sqlite:///" + str(directory / "authority.sqlite")
    store = RuntimeStore(url, artifacts)
    files = {"readme.txt": "Installed authored fixture; no candidate execution."}
    task = store.submit("installed-skills", "recovery", {
        "repo_id": "installed-authored-skills", "base_revision": tree_digest(files),
        "requirements": ["Recover captured skill knowledge under a fresh owner"], "model": MODEL,
        "rate_snapshot": context_rates(), "capabilities": ["load_skill", "read_skill_resource"]})
    tenant, task_id = task["tenant_id"], task["task_id"]
    store.set_graph(tenant, task_id, 1, [{"node_id": "reader"}])
    grant = store.claim(tenant, task_id, "reader", "owner-0", 100, 300)
    materialize(directory / "workspace", files)
    workspace = Workspace(directory / "workspace", list(files))
    origin = directory / "origin" / "verified-repair-guide"
    shutil.copytree(Path(workloads.__file__).parent / "skills/verified-repair-guide", origin)
    config = default_skills_config({"origin_id": "installed-fixture", "scope": "fixture", "root_label": "guide"},
                                   "installed-v1", "installed-v1")
    capture = capture_skill_catalog([origin], artifacts, tenant, task_id, config)
    package = read_catalog_snapshot(artifacts, tenant, task_id, capture, config)["packages"][0]
    load_args = {"catalog_digest": capture["catalog_digest"], "package_digest": package["package_digest"]}
    read_args = {**load_args, "path": "references/checklist.md", "offset": 0, "limit": 8192}
    expected_bytes = package["resources"][read_args["path"]]
    checkpoint_ids, loaded_counts, wires, epochs, restore_records = [], [], [], [], []
    restored = None
    primary = None
    try:
        for turn in range(3):
            owner = grant["owner"]
            epochs.append(owner["node_epoch"])

            def handler(request):
                wire = bytes(request.content)
                payload = json.loads(wire)
                active = [d for d in store.read_skill_proof(owner)["dispatches"]
                          if d["kind"] == "model.nebius" and d["effect_state"] == "in_flight"]
                require(len(active) == 1, "installed request lacks unique accepted intent")
                manifest = active[0]["context_acceptance"]["manifest"]
                saved = artifacts.get_json(tenant, task_id, manifest["request_ref"]["digest"])
                observed_digest = digest_json({**saved, "payload": payload})
                require(observed_digest == digest_json(saved) == active[0]["input_digest"] == manifest["request_digest"],
                        "installed native request differs from accepted bytes")
                state = artifacts.get_json(tenant, task_id, manifest["skills_state_ref"]["digest"])
                loaded_counts.append(len(state["loaded"]))
                if restored is not None:
                    require(canonical_bytes(payload["messages"][1:]) == canonical_bytes(restored["messages"]),
                            "native recovery changed raw history")
                    require(canonical_bytes(state["loaded"]) == canonical_bytes([primary]),
                            "fresh owner rewrote original receipt provenance")
                    require(manifest["binding"]["owner"] == owner and
                            manifest["binding"]["expected_previous_projection_id"] is None and
                            manifest["source_checkpoint"] == restored["source_checkpoint"],
                            "skills recovery reused old owner/chain or lost checkpoint lineage")
                wires.append({"turn": turn, "wire_sha256": sha(wire), "request_digest": active[0]["input_digest"],
                              "observed_canonical_wrapper_sha256": observed_digest})
                write_json(directory / (f"request-{turn}.json"), payload)
                (directory / f"request-{turn}.wire.json").write_bytes(wire)
                write_json(directory / f"request-{turn}.accepted.json", saved)
                write_json(directory / f"request-{turn}.dispatch.json", active[0])
                result = native_response("load_skill", load_args, "load") if turn == 0 else (
                    native_response("read_skill_resource", read_args, "read") if turn == 1 else native_response())
                if turn == 0:
                    result["choices"][0]["message"]["tool_calls"].append({
                        "id": "same-response-read", "type": "function", "function": {
                            "name": "read_skill_resource", "arguments": json.dumps(read_args)}})
                result["choices"][0]["message"]["reasoning_content"] = "installed opaque native field"
                return httpx.Response(200, json=result)

            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                model = NebiusChatCompletions("synthetic-mock-only", MODEL, enable_network=True, client=client)
                harness = Harness(store, artifacts, max_turns=4, provider_envelopes={MODEL: context_rates()},
                                  context_config=default_context_config(), skills_capture=capture, skills_config=config)
                result = harness.run(owner, task["contract"], workspace, model, restored=restored,
                                     pause_after_turn=turn + 1 if turn < 2 else None)
            checkpoint_ids.append(result["checkpoint_id"])
            snapshot = store.snapshot(tenant, task_id)
            checkpoint = next(c for c in snapshot["checkpoints"] if c["checkpoint_id"] == result["checkpoint_id"])
            require(checkpoint["manifest"]["schema"] == 3 and checkpoint["manifest"]["kind"] == "harness_skills_v1",
                    "skills turn failed to emit typed post-turn checkpoint")
            require(result["status"] == ("paused" if turn < 2 else "completion_proposed"),
                    "skills pause/completion boundary differs")
            if turn == 0:
                load = next(d for d in snapshot["dispatches"] if d["kind"] == "load_skill")
                primary = {"package_digest": package["package_digest"], "load_dispatch_id": load["dispatch_id"],
                           "result_ref": load["result_ref"]}
                denied = next(d for d in snapshot["dispatches"] if d["kind"] == "read_skill_resource")
                denied_result = artifacts.get_json(tenant, task_id, denied["result_ref"]["digest"])
                require(denied["effect_state"] == "failed_known" and denied["billing_state"] == "settled" and
                        denied["bound_units"] == 0 and denied_result["ok"] is False and
                        denied_result["error_type"] == "SkillError" and denied_result["message"] == "not_disclosed",
                        "same-response read obtained resource or wrong invariant failed")
                (origin / read_args["path"]).write_bytes(b"changed origin must never be used")
            if turn == 1:
                read = next(d for d in snapshot["dispatches"] if d["owner"] == owner and d["kind"] == "read_skill_resource")
                read_result = artifacts.get_json(tenant, task_id, read["result_ref"]["digest"])
                require(read_result["ok"] and base64.b64decode(read_result["value"]["data"], validate=True) == expected_bytes,
                        "recovered resource differs from immutable installed capture")
            store.retire_sandbox(tenant, grant["sandbox_id"], {"exit_observed": True, "supervisor": "installed-no-process-fixture"})
            if turn < 2:
                store.close()
                artifacts = LocalArtifacts(directory / "artifacts")
                store = RuntimeStore(url, artifacts)
                before_restore = store.snapshot(tenant, task_id)
                restored = restore_checkpoint(store, artifacts, tenant, task_id, result["checkpoint_id"])
                require(store.snapshot(tenant, task_id) == before_restore and "owner" not in restored and
                        "grants none" in restored["authority"], "skills restore mutated/granted execution authority")
                require(canonical_bytes(restored["messages"]) == canonical_bytes(result["messages"]),
                        "skills restore changed exact retained native history")
                write_json(directory / f"restore-{turn}.json", restored)
                restore_records.append({"source_checkpoint": restored["source_checkpoint"],
                                        "authority": restored["authority"], "runtime_unchanged": True})
                grant = store.claim(tenant, task_id, "reader", f"owner-{turn + 1}", 100, 300)
        require(result["status"] == "completion_proposed" and loaded_counts == [0, 1, 1], "installed state trace differs")
        final = store.snapshot(tenant, task_id)
        require(len(final["checkpoints"]) == 3 and all(s["status"] == "retired" for s in final["sandboxes"]),
                "installed typed checkpoint/retirement differs")
        require(epochs == [1, 2, 3], "skills owners failed to advance epoch across clean reopens")
        write_json(directory / "snapshot.json", final)
        return {"mock_requests": 3, "clean_reopens": 2, "accepted_loaded_counts": loaded_counts,
                "checkpoint_ids": checkpoint_ids, "original_primary": primary, "wire_records": wires,
                "owner_epochs": epochs, "restores": restore_records,
                "origin_mutation_ignored": True, "same_response_read_denied": True}
    finally:
        store.close()


def configured_service_case(directory, files, forbidden):
    import time
    from fastapi.testclient import TestClient
    import service.offline_server as server_module
    from service.offline_server import OfflineService
    from service.serving_config import fixture_contract, load_tokens
    from workloads import list_tasks

    directory.mkdir()
    contract = fixture_contract(list_tasks(tier="T1")[0].task_id, time.time() + 300, time.time() + 3600)
    config = {"schema": 1, "mode": "offline_fixture_v1", "root": str(directory / "runtime"),
              "host": "127.0.0.1", "port": 8765,
              "limits": {"service_slot_limit": 3, "tenant_slot_limit": 3,
                         "service_budget_units": 100000, "tenant_budget_units": 100000},
              "admission_policy": {"schema": 1, "service_pending_limit": 2, "tenant_pending_limit": 1},
              "worker": {"poll_ms": 100, "shutdown_seconds": 10},
              "principals": [{"tenant_id": "installed", "subject_id": "operator", "repositories": [contract["repo_id"]],
                              "can_review": True, "profiles": ["production"], "token_env": "CAM_SERVE_TOKEN_LOCAL"}],
              "catalog": [contract]}
    credential = "synthetic-installed-service-credential"
    headers = {"Authorization": "Bearer " + credential}
    tokens = load_tokens(config, {"CAM_SERVE_TOKEN_LOCAL": credential})
    request = {"key": "installed-fixture", "contract": contract}
    pids, worker_records, launches = [], [], []
    task_id = None
    completed_snapshot = None
    for restart in range(2):
        service = OfflineService(config, tokens)
        origin_file = directory / f"worker-{restart}.origins.json"
        original_popen = server_module.subprocess.Popen

        def observed_worker(argv, **kwargs):
            require(argv[:5] == [sys.executable, "-I", "-m", "service.offline_server", "_worker"],
                    "unexpected child launch during configured service observation")
            require(kwargs["cwd"] == service.root and len(kwargs["pass_fds"]) == 2,
                    "actual worker launch lost configured cwd/ownership descriptors")
            require(set(kwargs["env"]) == {"PATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE"},
                    "worker environment unexpectedly expanded")
            launches.append({"original_argv": argv, "cwd": str(kwargs["cwd"]), "env": kwargs["env"],
                             "inherited_fd_count": len(kwargs["pass_fds"]),
                             "instrumentation": "socket denial and origin capture around installed module main"})
            return original_popen([sys.executable, "-I", "-c", WORKER_GUARD, str(origin_file), *argv[4:]], **kwargs)

        # This seam is restored before any other acceptance subprocess is run.
        server_module.subprocess.Popen = observed_worker
        try:
            with TestClient(service.app()) as client:
                require(client.get("/ready").status_code == 200, "installed service not ready")
                require(client.get("/catalog").status_code == 401, "installed catalog exposed without credentials")
                require(client.get("/catalog", headers=headers).json()["contracts"] == [contract], "installed catalog differs")
                submitted = client.post("/tasks", headers=headers, json=request)
                require(submitted.status_code == 202, "installed submission rejected")
                current = submitted.json()["task_id"]
                require(task_id is None or current == task_id, "installed restart changed durable task ID")
                task_id = current
                pids.append(service.worker.pid)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    snapshot = service.store.snapshot("installed", task_id)
                    if snapshot["task"]["execution_state"] in {"review_eligible", "failed"}:
                        break
                    time.sleep(.05)
                require(snapshot["task"]["execution_state"] == "review_eligible" and
                        snapshot["task"]["review_state"] == "pending",
                        "installed fixture did not reach separate review boundary")
                require(all(s["status"] == "retired" for s in snapshot["sandboxes"]), "installed service retained completed slot")
                if completed_snapshot is not None:
                    for key in ("dispatches", "attempts", "candidates", "verifications", "budget"):
                        require(snapshot[key] == completed_snapshot[key], "clean service restart repeated completed work")
                repeated = client.post("/tasks", headers=headers, json=request)
                require(repeated.status_code == 202 and repeated.json()["task_id"] == task_id,
                        "installed duplicate submission changed task identity")
                duplicate_snapshot = service.store.snapshot("installed", task_id)
                for key in ("dispatches", "attempts", "candidates", "verifications", "budget"):
                    require(duplicate_snapshot[key] == snapshot[key], "duplicate submission repeated execution")
                completed_snapshot = duplicate_snapshot
        finally:
            server_module.subprocess.Popen = original_popen
        require(service.worker.poll() == 0, "installed worker did not stop cleanly")
        records = json.loads(origin_file.read_text())
        require(records["pid"] == service.worker.pid and Path(records["executable"]).resolve() == Path(sys.executable).resolve(),
                "worker origin evidence came from a different process/interpreter")
        validate_origins(records["origins"], files, forbidden)
        require({"service.offline_server", "service.engine", "service.harness", "service.storage"} <=
                records["origins"].keys(), "actual worker omitted expected executed product modules")
        worker_records.append(records)
    require(len(pids) == 2 and pids[0] != pids[1], "clean restart reused worker process")
    write_json(directory / "worker-launches.json", launches)
    write_json(directory / "snapshot.json", snapshot)
    return {"task_id": task_id, "worker_pids": pids, "clean_restarts": 1, "installed_worker_origins": worker_records,
            "duplicate_execution_unchanged": True, "completed_restart_execution_unchanged": True,
            "worker_instrumentation": "installed entrypoint/args/env/fds preserved with test-only socket/origin wrapper",
            "transport": "ASGI plus actual child process; independent review owns unmodified loopback HTTP",
            "paid_execution": False}


def gpu_plan_case(directory, files):
    from compute.gpu_contract import ROOT, SCHEMA
    import compute.rmsnorm_cuda as probe_module
    config = {"schema": SCHEMA, "mode": "trusted_authored", "paid_execution": False,
              "device": {"uuid": "GPU-00112233-4455-6677-8899-aabbccddeeff", "partition": "whole_gpu",
                         "sharing": "exclusive_operator_declared", "reservation": "whole_device_capacity"},
              "host": {"deadline_seconds": 120, "max_output_bytes": 1048576}, "seed": 20261011}
    original_launcher = probe_module.bounded_process

    def forbidden_launch(*args, **kwargs):
        raise AssertionError("disabled GPU plan attempted a child launch")

    probe_module.bounded_process = forbidden_launch
    try:
        result = probe_module.run_trusted_probe(config, execute=False)
    finally:
        probe_module.bounded_process = original_launcher
    require(result["observation"]["status"] == "not_run", "installed GPU planner executed work")
    require("torch" not in sys.modules, "disabled GPU planner imported optional torch")
    require(result["observation"]["lifecycle"]["gpu_may_have_started"] is False and
            result["observation"]["checks"] == result["observation"]["samples"] == [],
            "disabled GPU plan reported hardware work")
    for relative, observed in result["plan"]["source_hashes"].items():
        require(relative in files and observed == sha((ROOT / relative).read_bytes()) == files[relative]["sha256"],
                "installed GPU plan source differs from frozen manifest")
    lock = ROOT / "uv.lock"
    require(result["plan"]["lock_digest"] == (sha(lock.read_bytes()) if lock.exists() else None),
            "installed GPU plan invented missing lock identity")
    directory.mkdir()
    write_json(directory / "plan.json", result)
    return {"status": "not_run", "plan_digest": result["plan"]["plan_digest"], "torch_imported": False,
            "child_launch_denied_by_control": True, "source_hashes": result["plan"]["source_hashes"],
            "installed_lock_presence": lock.exists(), "installed_lock_digest": result["plan"]["lock_digest"]}


def environment_journal_case(directory, image):
    from service.artifacts import LocalArtifacts, digest_json
    from service.environment_recovery import (
        DockerEnvironmentBackend, EnvironmentLifecycle, read_observation, reconcile_environment,
    )
    from service.execution import tree_digest
    from service.repair_demo import demo_inputs
    from service.repair_verification import PythonFunctionVerifier
    from service.storage import RuntimeStore

    directory.mkdir()
    artifacts = LocalArtifacts(directory / "artifacts")
    store = RuntimeStore("sqlite:///" + str(directory / "authority.sqlite"), artifacts)
    repository, recipe, _, _ = demo_inputs()
    verifier = PythonFunctionVerifier(image)
    backend = DockerEnvironmentBackend("installed-local-docker")
    task = store.submit("installed-journal", "actual-verifier", {
        "repo_id": repository.repo_id, "base_revision": tree_digest(dict(repository.files)),
        "requirements": ["Measure the authored wrong candidate through a journaled Docker verifier"],
        "grader_digest": recipe.grader_digest, "environment_digest": verifier.environment_for(recipe)})
    tenant, task_id = task["tenant_id"], task["task_id"]
    reservation = store.reserve_environment(tenant, task_id, 1, "verifier", "installed-journal")
    lifecycle = EnvironmentLifecycle(store, artifacts, tenant, task_id, reservation["sandbox_id"], backend)
    try:
        result = verifier.verify(dict(repository.files), recipe, purpose="worker",
                                 sandbox_id=reservation["sandbox_id"], lifecycle=lifecycle)
        require(result["passed"] is False and result["outcome"] == "fail" and
                result["boundary_failures"] == [] and result["retirement"]["retired"] is True and
                any(c["category"] == "assertion_mismatch" for c in result["cases"]),
                "wrong installed candidate passed or physical retirement is uncertain")
        require(result["tree_digest"] == task["contract"]["base_revision"] and
                result["grader_digest"] == recipe.grader_digest and
                result["environment_digest"] == verifier.environment_for(recipe),
                "journaled verification result identity differs")
        lifecycle.close()
        row = store.read_environment_journal(tenant, reservation["sandbox_id"])
        journal = row["environment_journal"]
        require(row["status"] == "retired" and journal["phase"] == "retired", "installed journal slot not retired")
        require(len(journal["instances"]) == len(recipe.as_dict()["worker_cases"]), "installed verifier omitted journaled cases")
        require(all(i["state"] == "retired" and i["container_id"] and i["create_observation_ref"]
                    and i["retirement_observation_ref"] for i in journal["instances"]), "incomplete physical instance proof")
        observations = []
        for instance in journal["instances"]:
            require(re.fullmatch(r"[0-9a-f]{64}", instance["container_id"]) is not None,
                    "journal lacks exact immutable container ID")
            pair = {}
            for key, kind, status in (("create_observation_ref", "create", "bound"),
                                      ("retirement_observation_ref", "retirement", "absent")):
                value = read_observation(artifacts, tenant, task_id, instance[key])
                require(value["kind"] == kind and value["status"] == status and
                        value["container_id"] == instance["container_id"] and
                        value["backend"] == journal["backend"] and
                        value["creation_nonce"] == instance["creation_nonce"] and
                        value["intent_id"] == instance["intent_id"] and
                        value["launch_digest"] == digest_json(instance["launch"]),
                        "journal terminal observation differs from exact physical identity")
                pair[kind] = value
            absent = command(["docker", "ps", "-a", "--no-trunc", "--filter", "id=" + instance["container_id"],
                              "--format", "{{.ID}}"], directory, f"container-{instance['ordinal']}-absence")
            require(absent.strip() == "", "journal retired a still-present Docker instance")
            observations.append(pair)
        before = store.snapshot(tenant, task_id)
        repeated = reconcile_environment(lifecycle)
        require(repeated["status"] == "retired" and store.snapshot(tenant, task_id) == before,
                "known cleanup retry mutated authority")
        require(before["verifications"] == [] and before["budget"]["spent"] == 0,
                "physical bookkeeping manufactured verification or money")
        write_json(directory / "journal.json", row)
        write_json(directory / "terminal-observations.json", observations)
        write_json(directory / "verification-result.json", result)
        return {"instances": len(journal["instances"]), "states": [i["state"] for i in journal["instances"]],
                "container_ids": [i["container_id"] for i in journal["instances"]],
                "backend": journal["backend"], "wrong_candidate_rejected": True,
                "cleanup_retry_read_only": True, "paid_execution": False}
    finally:
        try:
            reconcile_environment(lifecycle)
        finally:
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sandbox-image", required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--forbidden-root", type=Path, action="append", required=True)
    args = parser.parse_args()
    require(sys.flags.isolated == 1, "acceptance requires Python -I")
    require(sys.prefix != sys.base_prefix, "acceptance requires a virtualenv")
    config = Path(sys.prefix) / "pyvenv.cfg"
    require("include-system-site-packages = false" in config.read_text().lower(), "system site packages enabled")
    forbidden = [p.resolve() for p in args.forbidden_root]
    require(not any(Path.cwd().resolve().is_relative_to(p) for p in forbidden), "cwd overlaps forbidden source")
    for entry in sys.path:
        require(entry and not any(Path(entry).resolve().is_relative_to(p) for p in forbidden),
                "import path overlaps forbidden source")
    output = args.output.resolve()
    require(not any(output.is_relative_to(p) for p in forbidden), "output overlaps forbidden source")
    output.mkdir(parents=True, exist_ok=False)
    summary = {"schema": 1, "status": "running", "evidence_kind": "installed_native_mock_local_docker_only",
               "live_model_claim": False, "human_mastery": "not assessed", "paid_execution": "disabled",
               "source_manifest_sha256": sha(args.source_manifest.read_bytes()), "python": sys.version,
               "executable": sys.executable, "prefix": sys.prefix, "cwd": str(Path.cwd()),
               "forbidden_roots": list(map(str, forbidden))}
    try:
        deny_network()
        files = manifest_files(args.source_manifest)
        summary["assets"] = installed_assets(files)
        summary["preflight_origins"] = origins(files, forbidden)
        require(re.fullmatch(r"(?:[A-Za-z0-9._:/-]+@)?sha256:[0-9a-f]{64}", args.sandbox_image) is not None,
                "immutable local image required")
        image_info = json.loads(command(["docker", "image", "inspect", args.sandbox_image], output, "docker-image"))
        require(len(image_info) == 1, "local image identity ambiguous")
        summary["docker_image"] = {k: image_info[0].get(k) for k in ("Id", "RepoDigests", "Architecture", "Os")}
        summary["requested_image"] = args.sandbox_image
        summary["qualification"] = qualification_case(output / "qualification-slice", args.sandbox_image)
        summary["qualification_process_origins"] = {
            path.relative_to(output).as_posix(): validate_origins(json.loads(path.read_text()), files, forbidden)
            for path in sorted((output / "qualification-slice").glob("*.origins.json"))}
        require(len(summary["qualification_process_origins"]) == 7, "qualification CLI origin inventory incomplete")
        summary["repair"] = repair_checks(output, args.sandbox_image)
        summary["repair_process_origins"] = {
            path.name: validate_origins(json.loads(path.read_text()), files, forbidden)
            for path in sorted(output.glob("*.origins.json"))}
        summary["context"] = context_case(output / "context")
        summary["unknown"] = context_case(output / "context-unknown", lost_response=True)
        summary["skills_recovery"] = skills_recovery_case(output / "skills-recovery")
        summary["configured_service"] = configured_service_case(output / "configured-service", files, forbidden)
        summary["gpu_plan"] = gpu_plan_case(output / "gpu-plan", files)
        summary["environment_journal"] = environment_journal_case(output / "environment-journal", args.sandbox_image)
        summary["product_module_origins"] = origins(files, forbidden)
        summary["distribution"] = {"name": "coding-agent-mastery",
                                   "version": importlib.metadata.version("coding-agent-mastery")}
        summary["status"] = "passed"
    except Exception as error:
        summary["status"] = "failed"
        summary["failure"] = {"type": type(error).__name__, "detail": str(error)}
        raise
    finally:
        write_json(output / "acceptance.json", summary)
    print(json.dumps({"status": summary["status"], "output": str(output),
                      "summary_sha256": sha((output / "acceptance.json").read_bytes())}))


if __name__ == "__main__":
    main()
