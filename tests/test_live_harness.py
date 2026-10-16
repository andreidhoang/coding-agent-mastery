import json

import httpx
import pytest
from service.artifacts import LocalArtifacts
from service.billing import ProviderEnvelope
from service.storage import RuntimeStore
from service.harness import Harness
from service.providers import AnthropicMessages
from service.execution import Workspace, materialize, tree_digest
from service.protocol import ProtocolError


def envelope():
    return {
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
        "bound_evidence": "synthetic mock context bound only",
        "max_request_bytes": 65536,
    }


def setup(tmp_path):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "db"), artifacts)
    contract = {
        "repo_id": "fixture",
        "base_revision": tree_digest({"a.py": "old"}),
        "requirements": ["read then propose completion"],
        "model": "pinned-test-model",
        "capabilities": ["read_file", "finish"],
        "rate_snapshot": envelope(),
    }
    task = store.submit("tenant", "key", contract)
    store.set_graph("tenant", task["task_id"], 1, [{"node_id": "n"}])
    owner = store.claim("tenant", task["task_id"], "n", "claim", 100, 60)["owner"]
    materialize(tmp_path / "workspace", {"a.py": "old"})
    return store, artifacts, task, owner, Workspace(tmp_path / "workspace", ["a.py"])


def test_live_adapter_runs_through_durable_harness_with_mock_http(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    calls = []

    def transport(request):
        calls.append(request)
        block = {"type": "tool_use", "id": "call1", "name": "read_file", "input": {"path": "a.py"}}
        raw = {
            "type": "message",
            "role": "assistant",
            "model": "pinned-test-model",
            "content": [block] if len(calls) == 1 else [],
            "stop_reason": "tool_use" if len(calls) == 1 else "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 8},
        }
        return httpx.Response(200, json=raw)

    model = AnthropicMessages(
        "mock-only",
        "pinned-test-model",
        enable_network=True,
        client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    harness = Harness(store, artifacts, provider_envelopes={model.model: envelope()})
    result = harness.run(owner, task["contract"], workspace, model)
    assert result["status"] == "completion_proposed" and len(calls) == 2
    state = store.snapshot("tenant", task["task_id"])
    assert state["budget"]["spent"] == 2
    assert state["task"]["execution_state"] != "review_eligible"
    assert all(d["billing_state"] == "settled" for d in state["dispatches"])
    assert all(
        artifacts.get("tenant", task["task_id"], e["response_ref"]["digest"]) for e in result["evidence"]
    )


def test_gateway_rejects_client_supplied_unapproved_price(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    model = AnthropicMessages("mock-only", "pinned-test-model", enable_network=True)
    with pytest.raises(PermissionError, match="trusted gateway"):
        Harness(store, artifacts).run(owner, task["contract"], workspace, model)
    assert store.snapshot("tenant", task["task_id"])["dispatches"] == []


def test_transport_loss_preserves_full_billing_exposure(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)

    def transport(request):
        raise httpx.ReadTimeout("injected after request send")

    model = AnthropicMessages(
        "mock-only",
        "pinned-test-model",
        enable_network=True,
        client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    with pytest.raises(httpx.ReadTimeout):
        Harness(store, artifacts, provider_envelopes={model.model: envelope()}).run(
            owner, task["contract"], workspace, model
        )
    state = store.snapshot("tenant", task["task_id"])
    assert state["budget"]["reserved"] == 100
    assert state["dispatches"][0]["effect_state"] == "unknown"
    assert state["dispatches"][0]["bound_units"] == ProviderEnvelope(envelope(), model.model).bound_units



@pytest.mark.parametrize("reason,content", [
    ("max_tokens", [{"type": "tool_use", "id": "never-run", "name": "read_file", "input": {"path": "a.py"}}]),
    ("tool_use", [{"type": "tool_use", "id": "invalid", "name": "finish", "input": {"summary": []}}]),
    ("end_turn", [{"type": "tool_use", "id": "mismatch", "name": "read_file", "input": {"path": "a.py"}}]),
])
def test_unusable_message_settles_valid_usage_and_preserves_exact_body_without_tools(tmp_path, reason, content):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    raw = {"type": "message", "role": "assistant", "model": "pinned-test-model", "content": content,
           "stop_reason": reason, "usage": {"input_tokens": 12, "output_tokens": 100},
           "opaque_future_receipt": {"signature": "unaltered-opaque-fixture"}}
    body = json.dumps(raw, ensure_ascii=False, indent=2).encode() + b"\n"
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    model = AnthropicMessages("mock-only", "pinned-test-model", enable_network=True,
                              client=httpx.Client(transport=httpx.MockTransport(transport)))
    harness = Harness(store, artifacts, provider_envelopes={model.model: envelope()})
    for _ in range(2):
        with pytest.raises(ProtocolError):
            harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(requests) == 1  # Replays consume the same rejected immutable receipt.
    assert len(state["dispatches"]) == 1  # No proposed tool was dispatched.
    dispatch = state["dispatches"][0]
    assert dispatch["effect_state"] == "succeeded"  # A complete provider response was received.
    assert dispatch["billing_state"] == "settled"
    assert dispatch["actual_units"] == 3
    assert artifacts.get("tenant", task["task_id"], dispatch["result_ref"]["digest"]) == body
    assert workspace.snapshot() == {"a.py": "old"}
    assert state["task"]["execution_state"] != "review_eligible"


@pytest.mark.parametrize("usage", [None, {"input_tokens": 12},
                                  {"input_tokens": True, "output_tokens": 100},
                                  {"input_tokens": 12, "output_tokens": 100, "cache_read_input_tokens": -1}])
def test_missing_or_untrusted_usage_preserves_raw_receipt_and_billing_exposure(tmp_path, usage):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    raw = {"type": "message", "role": "assistant", "model": "pinned-test-model",
           "content": [], "stop_reason": "end_turn", "usage": usage}
    body = json.dumps(raw, indent=2).encode()
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, content=body)

    model = AnthropicMessages("mock-only", "pinned-test-model", enable_network=True,
                              client=httpx.Client(transport=httpx.MockTransport(transport)))
    harness = Harness(store, artifacts, provider_envelopes={model.model: envelope()})
    for _ in range(2):
        with pytest.raises(ProtocolError):
            harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    dispatch = state["dispatches"][0]
    assert dispatch["effect_state"] == "succeeded"
    assert dispatch["billing_state"] == "liability_unknown"
    assert dispatch["actual_units"] is None
    assert state["budget"]["reserved"] == 100
    assert len(requests) == 1 and len(state["dispatches"]) == 1
    assert artifacts.get("tenant", task["task_id"], dispatch["result_ref"]["digest"]) == body


@pytest.mark.parametrize("body", [b'{"usage":{"input_tokens":1,"input_tokens":2,"output_tokens":3}}',
                                 b'{"usage":{"input_tokens":1,"output_tokens":3},"extra":[1e999]}',
                                 b'\xff'])
def test_malformed_received_body_is_retained_but_never_reparsed_permissively_on_replay(tmp_path, body):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, content=body)

    model = AnthropicMessages("mock-only", "pinned-test-model", enable_network=True,
                              client=httpx.Client(transport=httpx.MockTransport(transport)))
    harness = Harness(store, artifacts, provider_envelopes={model.model: envelope()})
    for _ in range(2):
        with pytest.raises(ProtocolError):
            harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    dispatch = state["dispatches"][0]
    assert dispatch["billing_state"] == "liability_unknown"
    assert len(requests) == 1 and len(state["dispatches"]) == 1
    assert artifacts.get("tenant", task["task_id"], dispatch["result_ref"]["digest"]) == body
