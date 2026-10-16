import pytest

from service.artifacts import LocalArtifacts, digest_bytes, digest_json
from service.engine import ReferenceEngine
from service.execution import Workspace, materialize
from service.harness import ToolBroker
from service.protocol import ToolCall
from service.storage import RuntimeStore
from workloads import list_tasks


def runtime(tmp_path):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "state.sqlite"), artifacts)
    return store, artifacts, ReferenceEngine(store, artifacts, tmp_path / "workers")


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_full_fixture_preserves_review_boundary_and_replay(tmp_path, workers):
    store, artifacts, engine = runtime(tmp_path)
    task = engine.submit_fixture(list_tasks(tier="T3")[0].task_id, workers=workers)
    snapshot = engine.run_task("demo", task["task_id"])
    assert snapshot["task"]["execution_state"] == "review_eligible"
    assert snapshot["task"]["review_state"] == "pending"
    assert len(snapshot["nodes"]) == 2
    assert all(n["status"] == "completed" for n in snapshot["nodes"])
    assert all(d["effect_state"] == "succeeded" for d in snapshot["dispatches"])
    assert snapshot["budget"] == {"spent": 0, "reserved": 0, "limit": 1000}
    assert all(s["status"] == "retired" for s in snapshot["sandboxes"])
    count = len(snapshot["dispatches"])
    assert len(engine.run_task("demo", task["task_id"])["dispatches"]) == count
    store.close()


def test_crash_after_integration_resumes_saved_outputs(tmp_path, monkeypatch):
    store, artifacts, engine = runtime(tmp_path)
    task = engine.submit_fixture(list_tasks(tier="T3")[0].task_id)
    original = engine.verifier.verify
    monkeypatch.setattr(
        engine.verifier,
        "verify",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("injected verifier loss")),
    )
    with pytest.raises(RuntimeError, match="injected"):
        engine.run_task("demo", task["task_id"])
    before = store.snapshot("demo", task["task_id"])
    assert before["task"]["head_revision"] == 1
    monkeypatch.setattr(engine.verifier, "verify", original)
    after = engine.run_task("demo", task["task_id"])
    assert after["task"]["execution_state"] == "review_eligible"
    assert len(before["attempts"]) == len(after["attempts"])
    assert before["task"]["head_revision"] == after["task"]["head_revision"]


def test_ambiguous_tool_dispatch_is_not_reexecuted(tmp_path):
    store, artifacts, engine = runtime(tmp_path)
    task = engine.submit_fixture(list_tasks(tier="T3")[0].task_id)
    store.set_graph("demo", task["task_id"], 1, [{"node_id": "patch", "dependencies": []}])
    owner = store.claim("demo", task["task_id"], "patch", "claim", 100, 60)["owner"]
    materialize(tmp_path / "workspace", {"a.py": "old"})
    workspace = Workspace(tmp_path / "workspace", ["a.py"])
    call = ToolCall(
        "edit",
        "replace_text",
        {"path": "a.py", "expected_digest": digest_bytes(b"old"), "old": "old", "new": "new"},
    )
    identity = digest_json({"attempt": owner["attempt_id"], "call": call.call_id})
    store.begin_dispatch(
        owner, "action-" + identity[:32], "dispatch-" + identity[:32], call.name, call.digest, 0
    )
    workspace.replace("a.py", digest_bytes(b"old"), "old", "new")
    broker = ToolBroker(store, artifacts, owner, workspace, ["replace_text"])
    with pytest.raises(RuntimeError, match="unresolved"):
        broker.execute(call)
    assert workspace.read("a.py")["text"] == "new"
    dispatch = store.snapshot("demo", task["task_id"])["dispatches"][0]
    assert dispatch["effect_state"] == "in_flight" and dispatch["billing_state"] == "reserved"
