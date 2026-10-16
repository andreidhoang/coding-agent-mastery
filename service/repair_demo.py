"""Explicit native HTTP mock for local mechanics; never a learned repair claim."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .artifacts import digest_bytes
from .repair_provider import ProviderApproval
from .repair_verification import PythonFunctionRecipe
from .repositories import freeze_repository

MODEL = "nvidia/Nemotron-fixture"


def demo_inputs():
    from workloads.registry import ROOT

    task_path = ROOT / "repair/tasks/text-normalization-v1.json"
    task = json.loads(task_path.read_text())
    repository = freeze_repository(
        (task_path.parent / task["repository"]).resolve(), task["repo_id"],
        task["source_paths"], task["allowed_paths"],
    )
    recipe = PythonFunctionRecipe.from_dict(json.loads((task_path.parent / task["recipe"]).read_text()))
    rates = {
        "schema": 1, "unit": "micro_usd", "rate_id": "zero-cost-mock-only", "model": MODEL,
        "input_token_bound": 32768, "max_output_tokens": 1024,
        "input_per_million": 0, "output_per_million": 0,
        "cache_read_per_million": 0, "cache_write_per_million": 0,
        "bound_evidence": "fixture:synthetic-protocol-only; no provider rate claim", "max_request_bytes": 131072,
    }
    approval = ProviderApproval.from_dict({
        "schema": 1, "provider": "nebius", "protocol": "chat_completions",
        "endpoint": "https://api.tokenfactory.nebius.com/v1/", "model": MODEL,
        "rate_snapshot": rates, "max_response_bytes": 2000000,
        "evidence": {"kind": "mock", "identity": "fixture:owned-text-normalization-v1"},
    })
    return repository, recipe, approval, task["issue"]


def demo_adapter(approval):
    """Derive mock turn from retained native history, including across process restart."""
    requests = []

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        turns = sum(m["role"] == "assistant" for m in payload["messages"])
        if turns == 0:
            name, args = "read_file", {"path": "slug.py"}
        elif turns == 1:
            name, args = "run_tests", {}
        elif turns == 2:
            read = next(json.loads(m["content"])["value"] for m in payload["messages"]
                        if m["role"] == "tool" and json.loads(m["content"])["tool"] == "read_file")
            old = read["text"]
            new = (
                '"""Owned demonstration: lowercase ASCII words separated by hyphens."""\n'
                'import re\n\n\ndef normalize_slug(text):\n'
                '    if not isinstance(text, str):\n'
                '        raise TypeError("text must be a string")\n'
                '    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))\n'
            )
            name, args = "replace_text", {"path": "slug.py", "expected_digest": digest_bytes(old.encode()),
                                          "old": old, "new": new}
        elif turns == 3:
            name, args = "run_tests", {}
        else:
            name, args = "finish", {"summary": "Mock mechanics repair complete; independent checks pending"}
        call = {"id": f"demo-{turns}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}
        return httpx.Response(200, json={
            "id": f"mock-response-{turns}", "object": "chat.completion", "model": approval.model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [call],
                "reasoning_content": "synthetic fixture continuation; not model reasoning",
            }}], "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        })

    client = httpx.Client(transport=httpx.MockTransport(transport))
    return approval.build_adapter("mock-only", enable_network=True, client=client), requests


def run_demo(output: str | Path, image: str, *, pause_after_turn=None, resume=False):
    import time
    from .artifacts import LocalArtifacts
    from .repair import RepairEngine, committed_repair_events
    from .repair_reporting import write_repair_report
    from .repair_verification import PythonFunctionVerifier
    from .storage import RuntimeStore

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    repository, recipe, approval, issue = demo_inputs()
    artifacts = LocalArtifacts(output / "artifacts")
    private = LocalArtifacts(output / "control-inputs")
    store = RuntimeStore("sqlite:///" + str(output / "authority.sqlite"), artifacts)
    try:
        verifier = PythonFunctionVerifier(image, recipe=recipe)
        engine = RepairEngine(store, artifacts, output / "workspaces", verifier, private_inputs=private)
        identity_file = output / "repair-task.json"
        if identity_file.exists():
            task_id = json.loads(identity_file.read_text())["task_id"]
        else:
            task = engine.submit(repository, recipe, approval, issue, tenant="repair-demo", key="demo-v1",
                                 budget_units=0, execution_deadline=time.time() + 3600,
                                 review_deadline=time.time() + 86400)
            task_id = task["task_id"]
            identity_file.write_text(json.dumps({"schema": 1, "tenant": "repair-demo", "task_id": task_id,
                                                  "image": verifier.image}) + "\n")
        model, requests = demo_adapter(approval)
        try:
            snapshot = engine.run_task("repair-demo", task_id, model, resume=resume,
                                       pause_after_turn=pause_after_turn)
        finally:
            model.client.close()
        events = committed_repair_events(store, "repair-demo", task_id, snapshot)
        report = write_repair_report(output, snapshot, events, artifacts=artifacts)
        return {"task_id": task_id, "state": snapshot["task"]["execution_state"],
                "paused": snapshot.get("paused", False), "mock_requests_this_process": len(requests),
                "report": str(output / "repair.html"), "evidence_kind": snapshot["evidence_kind"],
                "verified": report["verified"]}
    finally:
        store.close()
