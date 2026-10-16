import sys
import httpx
import pytest
from service.execution import DockerSandbox, bounded_process
from service.providers import AnthropicMessages
from service.harness import Harness
from service.contracts import Fenced
from service.artifacts import LocalArtifacts, digest_json
from service.storage import RuntimeStore
from service.recovery import restore_checkpoint, recovery_plan
from service.execution import tree_digest, Workspace, materialize


def test_unacknowledged_container_create_never_claims_retirement(monkeypatch):
    calls = []

    def launch(argv, **kwargs):
        calls.append(argv)
        if "create" in argv:
            return {"exit_code": -9, "reason": "timeout", "output": b"", "duration_seconds": 30}
        return {"exit_code": 0, "reason": "exited", "output": b"", "duration_seconds": 0}

    monkeypatch.setattr("service.execution.bounded_process", launch)
    sandbox = DockerSandbox("sha256:" + "a" * 64)
    with pytest.raises(RuntimeError, match="unknown"):
        sandbox.start({"a.py": "print('x')"})
    assert any("ps" in call for call in calls)
    with pytest.raises(RuntimeError, match="unresolved"):
        sandbox.close()
    assert sandbox.provisioning_attempted


def test_launcher_input_backpressure_is_bounded():
    result = bounded_process(
        [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05, stdin=b"x" * 1048576
    )
    assert result["reason"] == "timeout"


def test_token_bound_violation_cannot_execute_tools_on_replay(tmp_path):
    rate = {
        "schema": 1,
        "unit": "micro_usd",
        "rate_id": "synthetic-test-rates",
        "model": "pinned-test-model",
        "input_token_bound": 100,
        "max_output_tokens": 100,
        "input_per_million": 10000,
        "output_per_million": 20000,
        "cache_read_per_million": 1000,
        "cache_write_per_million": 15000,
        "bound_evidence": "synthetic mock only",
        "max_request_bytes": 65536,
    }
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "db"), artifacts)
    task = store.submit(
        "tenant",
        "key",
        {
            "repo_id": "fixture",
            "base_revision": tree_digest({"a.py": "old"}),
            "requirements": ["read"],
            "model": "pinned-test-model",
            "rate_snapshot": rate,
            "capabilities": ["read_file"],
        },
    )
    store.set_graph("tenant", task["task_id"], 1, [{"node_id": "n"}])
    owner = store.claim("tenant", task["task_id"], "n", "claim", 100, 60)["owner"]
    materialize(tmp_path / "work", {"a.py": "old"})
    workspace = Workspace(tmp_path / "work", ["a.py"])
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "type": "message",
                "role": "assistant",
                "model": "pinned-test-model",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "forbidden-after-bound",
                        "name": "read_file",
                        "input": {"path": "a.py"},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 101, "output_tokens": 0},
            },
        )

    model = AnthropicMessages(
        "mock-only",
        "pinned-test-model",
        enable_network=True,
        client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    harness = Harness(store, artifacts, provider_envelopes={model.model: rate})
    with pytest.raises(RuntimeError, match="token-bound"):
        harness.run(owner, task["contract"], workspace, model)
    with pytest.raises(Fenced):
        harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(requests) == 1 and len(state["dispatches"]) == 1
    assert state["task"]["execution_state"] == "failed"
    assert state["dispatches"][0]["actual_units"] == 2


def test_checkpoint_uses_causal_dispatch_frontier_even_when_clocks_tie(tmp_path, monkeypatch):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "db"), artifacts)
    monkeypatch.setattr(store, "_now", lambda _: 1000.0)
    files = {"a.py": "source"}
    task = store.submit(
        "tenant",
        "key",
        {"repo_id": "fixture", "base_revision": tree_digest(files), "requirements": ["preserve state"]},
    )
    tid = task["task_id"]
    store.set_graph("tenant", tid, 1, [{"node_id": "n"}])
    owner = store.claim("tenant", tid, "n", "claim", 20, 60)["owner"]
    workspace = artifacts.put_json("tenant", tid, files)
    payload = artifacts.put_json("tenant", tid, {"messages": [], "evidence": [], "workspace_ref": workspace})
    checkpoint = store.checkpoint(owner, {"artifact_ref": payload, "next_turn": 0})
    restored = restore_checkpoint(store, artifacts, "tenant", tid, checkpoint["checkpoint_id"])
    assert restored["files"] == files and restored["workspace_digest"] == digest_json(files)
    dispatch = store.begin_dispatch(owner, "a", "d", "read", digest_json("input"), 5)
    store.finish_dispatch(
        "tenant", "d", "receipt", "succeeded", 3, artifacts.put_json("tenant", tid, {"result": "done"})
    )
    assert dispatch["created_at"] == checkpoint["created_at"]
    with pytest.raises(ValueError, match="post-checkpoint"):
        restore_checkpoint(store, artifacts, "tenant", tid, checkpoint["checkpoint_id"])


def test_unknown_recovery_plan_keeps_physical_and_billing_obligations():
    snapshot = {
        "quarantined": False,
        "task": {"execution_state": "cancelled"},
        "dispatches": [{"dispatch_id": "d", "effect_state": "unknown", "billing_state": "liability_unknown"}],
        "sandboxes": [{"sandbox_id": "s", "status": "retirement_requested"}],
        "budget": {"spent": 0, "reserved": 12},
        "frontier": {"sequence": 9},
    }
    plan = recovery_plan(snapshot)
    assert plan["next_step"] == "reconcile_effects_before_replacement"
    assert plan["unknown_dispatches"] == ["d"] and plan["unsettled_dispatches"] == ["d"]
    assert plan["retained_sandboxes"] == ["s"] and plan["budget"]["reserved"] == 12
