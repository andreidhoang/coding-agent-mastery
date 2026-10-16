"""Synthetic HTTP evidence only: no live endpoint, model capability or rate claim."""

import copy
import json

import httpx
import pytest

from service.artifacts import LocalArtifacts, digest_bytes, digest_json
from service.billing import ProviderEnvelope
from service.context import project_context
from service.execution import Workspace, materialize, tree_digest
from service.harness import Harness
from service.protocol import ProtocolError, validate_nebius_linkage
from service.providers import AnthropicMessages, NebiusChatCompletions, NebiusHTTPError, parse_nebius_usage
from service.recovery import restore_checkpoint
from service.storage import RuntimeStore

MODEL = "synthetic/NVIDIA-pinned-fixture"


def rates(**updates):
    value = {
        "schema": 1, "unit": "micro_usd", "rate_id": "synthetic-nebius-rates", "model": MODEL,
        "input_token_bound": 100, "max_output_tokens": 100,
        "input_per_million": 10000, "output_per_million": 20000,
        "cache_read_per_million": 1000, "cache_write_per_million": 15000,
        "bound_evidence": "mock-only bound; live max_tokens enforcement pending", "max_request_bytes": 65536,
    }
    value.update(updates)
    return value


def usage(**updates):
    value = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
             "prompt_tokens_details": {"cached_tokens": 30},
             "completion_tokens_details": {"reasoning_tokens": 12}}
    value.update(updates)
    return value


def call(identity="read", name="read_file", arguments=None):
    return {"id": identity, "type": "function", "function": {
        "name": name, "arguments": json.dumps({"path": "a.py"} if arguments is None else arguments),
    }}


def response(calls=None, *, reason=None, counters=None):
    return {"id": "synthetic-response", "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "finish_reason": reason or ("tool_calls" if calls else "stop"),
                         "message": {"role": "assistant", "content": None if calls else "proposed",
                                     **({"tool_calls": calls} if calls is not None else {})}}],
            "usage": usage() if counters is None else counters}


def setup(tmp_path, *, rate=None):
    rate = rate or rates()
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "db"), artifacts)
    contract = {"repo_id": "fixture", "base_revision": tree_digest({"a.py": "old"}),
                "requirements": ["read, edit, then propose finish"], "model": MODEL,
                "capabilities": ["read_file", "replace_text", "finish"], "rate_snapshot": rate}
    task = store.submit("tenant", "key", contract)
    store.set_graph("tenant", task["task_id"], 1, [{"node_id": "n"}])
    owner = store.claim("tenant", task["task_id"], "n", "claim", 100, 60)["owner"]
    materialize(tmp_path / "workspace", {"a.py": "old"})
    return store, artifacts, task, owner, Workspace(tmp_path / "workspace", ["a.py"])


def model_for(handler, **options):
    return NebiusChatCompletions("mock-only-never-real", MODEL, enable_network=True,
                                 client=httpx.Client(transport=httpx.MockTransport(handler),
                                                     follow_redirects=True), **options)


def harness_for(store, artifacts, **options):
    return Harness(store, artifacts, provider_envelopes={MODEL: rates()}, **options)


def test_native_read_edit_finish_preserves_opaque_history_and_intent_and_replays_once(tmp_path, monkeypatch):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    first = response([call()])
    opaque = {"reasoning_content": "opaque mock reasoning", "reasoning": [{"signature": "fixture"}],
              "provider_future_field": {"unchanged": [1, "x"]}}
    first["choices"][0]["message"].update(opaque)
    edit = call("edit", "replace_text", {"path": "a.py", "expected_digest": digest_bytes(b"old"),
                                          "old": "old", "new": "new"})
    finish = call("finish", "finish", {"summary": "proposal only"})
    bodies = [json.dumps(raw, indent=2).encode() + b"\n"
              for raw in (first, response([edit]), response([finish]))]
    requests, edits = [], []
    original_replace = workspace.replace

    def replace(*args):
        edits.append(args)
        return original_replace(*args)

    monkeypatch.setattr(workspace, "replace", replace)

    def handler(request):
        index = len(requests)
        payload = json.loads(request.content)
        requests.append(payload)
        state = store.snapshot("tenant", task["task_id"])
        dispatch = next(d for d in state["dispatches"] if d["dispatch_id"] == f"model-{owner['attempt_id']}-{index}")
        assert dispatch["effect_state"] == "in_flight" and dispatch["kind"] == "model.nebius"
        record = {"provider": "nebius", "protocol": "chat_completions",
                  "endpoint": NebiusChatCompletions.ENDPOINT, "payload": payload}
        assert dispatch["input_digest"] == digest_json(record)
        assert artifacts.get_json("tenant", task["task_id"], digest_json(record)) == record
        assert "mock-only-never-real" not in json.dumps(record)
        assert str(request.url) == NebiusChatCompletions.ENDPOINT + "chat/completions"
        assert request.headers["authorization"] == "Bearer mock-only-never-real"
        assert payload["model"] == MODEL and payload["n"] == 1 and payload["stream"] is False
        assert payload["max_tokens"] == 100 and payload["tool_choice"] == "auto"
        assert all(t["type"] == "function" for t in payload["tools"])
        if index:
            assert payload["messages"][2] == first["choices"][0]["message"]
            assert payload["messages"][3]["role"] == "tool"
            assert payload["messages"][3]["tool_call_id"] == "read"
            assert json.loads(payload["messages"][3]["content"])["value"]["text"] == "old"
        return httpx.Response(200, content=bodies[index])

    model = model_for(handler)
    harness = harness_for(store, artifacts)
    result = harness.run(owner, task["contract"], workspace, model)
    replay = harness.run(owner, task["contract"], workspace, model)
    assert replay == result
    assert len(requests) == 3 and len(edits) == 1 and workspace.snapshot() == {"a.py": "new"}
    assert result["status"] == "completion_proposed"
    validate_nebius_linkage(result["messages"])
    state = store.snapshot("tenant", task["task_id"])
    assert state["budget"]["spent"] == 6
    assert state["task"]["execution_state"] != "review_eligible"
    assert all(d["billing_state"] == "settled" for d in state["dispatches"])
    for index, item in enumerate(result["evidence"]):
        assert artifacts.get("tenant", task["task_id"], item["response_ref"]["digest"]) == bodies[index]
    checkpoint = next(c for c in state["checkpoints"] if c["manifest"]["next_turn"] == 3)
    restored = restore_checkpoint(store, artifacts, "tenant", task["task_id"], checkpoint["checkpoint_id"])
    assert restored["messages"] == result["messages"]


def test_checkpoint_native_continuation_and_adapter_drift_rejection(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []
    first = response([call()])
    first["choices"][0]["message"]["reasoning_content"] = "opaque checkpoint fixture"

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=first if len(requests) == 1 else response())

    model = model_for(handler)
    with pytest.raises(RuntimeError, match="turn budget"):
        harness_for(store, artifacts, max_turns=1).run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    restored = restore_checkpoint(store, artifacts, "tenant", task["task_id"],
                                  state["checkpoints"][0]["checkpoint_id"])
    assert restored["messages"][1] == first["choices"][0]["message"]
    foreign = AnthropicMessages("mock-only", MODEL, enable_network=True,
                                client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError, match="provider identity drift"):
        harness_for(store, artifacts).run(owner, task["contract"], workspace, foreign, restored=restored)
    result = harness_for(store, artifacts).run(owner, task["contract"], workspace, model, restored=restored)
    assert result["turns"] == 2 and len(requests) == 2
    assert requests[1]["messages"][2:] == restored["messages"][1:]


@pytest.mark.parametrize("fault", ["length", "content_filter", "missing_reason", "wrong_model", "wrong_role",
                                    "extra_choice", "invalid_arguments", "duplicate_id", "wrong_index",
                                    "unknown_tool", "empty_tools", "stop_with_tool"])
def test_invalid_semantics_settle_usage_retain_body_and_never_execute_or_rerequest(tmp_path, fault):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    raw = response([call("never", "replace_text", {"path": "a.py", "expected_digest": digest_bytes(b"old"),
                                                  "old": "old", "new": "new"})])
    choice = raw["choices"][0]
    message = choice["message"]
    if fault in {"length", "content_filter"}:
        choice["finish_reason"] = fault
    elif fault == "missing_reason":
        del choice["finish_reason"]
    elif fault == "wrong_model":
        raw["model"] = "unapproved-alias"
    elif fault == "wrong_role":
        message["role"] = "user"
    elif fault == "extra_choice":
        raw["choices"].append(copy.deepcopy(choice))
    elif fault == "invalid_arguments":
        message["tool_calls"][0]["function"]["arguments"] = '{"path":"a.py","path":"other"}'
    elif fault == "duplicate_id":
        message["tool_calls"].append(copy.deepcopy(message["tool_calls"][0]))
    elif fault == "wrong_index":
        choice["index"] = True
    elif fault == "unknown_tool":
        message["tool_calls"][0]["function"]["name"] = "read_secrets"
    elif fault == "empty_tools":
        message["tool_calls"] = []
    elif fault == "stop_with_tool":
        choice["finish_reason"] = "stop"
    body = json.dumps(raw, indent=2).encode() + b"\n"
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=body)

    model, harness = model_for(handler), harness_for(store, artifacts)
    for _ in range(2):
        with pytest.raises(ProtocolError):
            harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(requests) == len(state["dispatches"]) == 1
    dispatch = state["dispatches"][0]
    assert dispatch["effect_state"] == "succeeded"
    if fault == "wrong_model":
        assert dispatch["billing_state"] == "liability_unknown" and dispatch["actual_units"] is None
        assert state["budget"]["spent"] == 0 and state["budget"]["reserved"] == 100
    else:
        assert dispatch["billing_state"] == "settled"
        assert dispatch["actual_units"] == 2 and state["budget"]["spent"] == 2
    assert artifacts.get("tenant", task["task_id"], dispatch["result_ref"]["digest"]) == body
    assert workspace.snapshot() == {"a.py": "old"}


@pytest.mark.parametrize("bad_usage", [None, {}, {"prompt_tokens": 1}, usage(prompt_tokens=True),
                                       usage(completion_tokens=-1), usage(prompt_tokens=2**63),
                                       usage(total_tokens=121),
                                       usage(prompt_tokens_details={"cached_tokens": 101}),
                                       usage(completion_tokens_details={"reasoning_tokens": 21}),
                                       usage(prompt_tokens_details={"cached_tokens": False}),
                                       usage(completion_tokens_details=[]),
                                       usage(completion_tokens_details={"reasoning_tokens": 1e999})])
def test_untrusted_usage_retains_liability_and_raw_receipt_without_retry(tmp_path, bad_usage):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    raw = response([call()])
    raw["usage"] = bad_usage
    body = json.dumps(raw).encode()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=body)

    model, harness = model_for(handler), harness_for(store, artifacts)
    for _ in range(2):
        with pytest.raises(ProtocolError):
            harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(requests) == len(state["dispatches"]) == 1
    dispatch = state["dispatches"][0]
    assert dispatch["effect_state"] == "succeeded" and dispatch["billing_state"] == "liability_unknown"
    assert dispatch["actual_units"] is None and state["budget"]["reserved"] == 100
    assert artifacts.get("tenant", task["task_id"], dispatch["result_ref"]["digest"]) == body


def test_cached_and_reasoning_subsets_are_disjoint_and_integer_charge_rounds_once():
    normalized = parse_nebius_usage({"usage": usage()})
    assert normalized == {"input_tokens": 70, "cache_read_input_tokens": 30, "output_tokens": 20}
    assert ProviderEnvelope(rates(), MODEL).charge(normalized) == 2
    zero = parse_nebius_usage({"usage": {"prompt_tokens": 0, "completion_tokens": 0}})
    assert ProviderEnvelope(rates(), MODEL).charge(zero) == 0
    all_cached = parse_nebius_usage({"usage": usage(prompt_tokens_details={"cached_tokens": 100})})
    assert all_cached["input_tokens"] == 0 and all_cached["cache_read_input_tokens"] == 100


@pytest.mark.parametrize("counter,value", [("prompt_tokens", 101), ("completion_tokens", 101)])
def test_provider_token_violation_is_settled_before_run_revocation(tmp_path, counter, value):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    counters = usage(**{counter: value})
    counters["total_tokens"] = counters["prompt_tokens"] + counters["completion_tokens"]
    raw = response([call()], counters=counters)
    model = model_for(lambda request: httpx.Response(200, json=raw))
    with pytest.raises(RuntimeError, match="token-bound violation"):
        harness_for(store, artifacts).run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(state["dispatches"]) == 1 and state["dispatches"][0]["billing_state"] == "settled"
    assert state["task"]["execution_state"] == "failed"


def test_timeout_once_preserves_unknown_and_full_exposure(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("synthetic response lost")

    model, harness = model_for(handler), harness_for(store, artifacts)
    with pytest.raises(httpx.ReadTimeout):
        harness.run(owner, task["contract"], workspace, model)
    with pytest.raises(RuntimeError, match="unresolved model dispatch"):
        harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(requests) == len(state["dispatches"]) == 1
    assert state["dispatches"][0]["effect_state"] == "unknown"
    assert state["dispatches"][0]["bound_units"] == ProviderEnvelope(rates(), MODEL).bound_units
    assert state["budget"]["reserved"] == 100


def test_disabled_and_unapproved_envelopes_send_nothing(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    disabled = NebiusChatCompletions("mock-only", MODEL,
                                     client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(PermissionError, match="disabled"):
        disabled.request([], "policy")
    with pytest.raises(PermissionError, match="explicitly enabled"):
        harness_for(store, artifacts).run(owner, task["contract"], workspace, disabled)
    with pytest.raises(PermissionError, match="trusted gateway"):
        Harness(store, artifacts).run(owner, task["contract"], workspace, model_for(handler))
    assert not requests and not store.snapshot("tenant", task["task_id"])["dispatches"]


@pytest.mark.parametrize("endpoint", ["http://api.tokenfactory.nebius.com/v1/", "https://evil.invalid/v1/",
                                      "https://api.tokenfactory.nebius.com/v1/?redirect=evil",
                                      "https://api.tokenfactory.nebius.com.evil.invalid/v1/"])
def test_unapproved_endpoint_rejected(endpoint):
    with pytest.raises(ValueError, match="unapproved Nebius endpoint"):
        NebiusChatCompletions("mock-only", MODEL, endpoint=endpoint)


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_not_followed_even_with_redirect_enabled_client(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"location": "https://evil.invalid/"})

    with pytest.raises(NebiusHTTPError):
        model_for(handler).request([], "policy")
    assert len(requests) == 1


@pytest.mark.parametrize("body", [b'{"usage":{"prompt_tokens":1,"prompt_tokens":2,"completion_tokens":3}}',
                                  b'{"usage":{"prompt_tokens":1,"completion_tokens":3},"x":1e999}',
                                  b'\xff', b'{"usage":'])
def test_invalid_complete_body_is_persisted_before_strict_decode(tmp_path, body):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=body)

    model, harness = model_for(handler), harness_for(store, artifacts)
    for _ in range(2):
        with pytest.raises(ProtocolError):
            harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    dispatch = state["dispatches"][0]
    assert dispatch["billing_state"] == "liability_unknown" and len(requests) == 1
    assert artifacts.get("tenant", task["task_id"], dispatch["result_ref"]["digest"]) == body


def test_response_byte_overflow_is_unknown_not_complete_receipt(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    model = model_for(lambda request: httpx.Response(200, content=b" " * 65), max_response_bytes=64)
    with pytest.raises(ProtocolError, match="byte bound"):
        harness_for(store, artifacts).run(owner, task["contract"], workspace, model)
    dispatch = store.snapshot("tenant", task["task_id"])["dispatches"][0]
    assert dispatch["effect_state"] == "unknown" and dispatch["result_ref"] is None


def test_request_and_context_byte_limits_prevent_any_dispatch(tmp_path):
    rate = rates(max_request_bytes=10)
    store, artifacts, task, owner, workspace = setup(tmp_path, rate=rate)
    model = model_for(lambda request: pytest.fail("must not send HTTP"))
    with pytest.raises(ValueError, match="request byte bound"):
        Harness(store, artifacts, provider_envelopes={MODEL: rate}).run(owner, task["contract"], workspace, model)
    with pytest.raises(ValueError, match="context byte budget"):
        Harness(store, artifacts, context_bytes=10, provider_envelopes={MODEL: rate}).run(
            owner, task["contract"], workspace, model)
    assert not store.snapshot("tenant", task["task_id"])["dispatches"]


@pytest.mark.parametrize("history", [
    [{"role": "tool", "tool_call_id": "read", "content": "orphan"}],
    [{"role": "assistant", "content": None, "tool_calls": [call()]}],
    [{"role": "assistant", "content": None, "tool_calls": [call()]},
     {"role": "user", "content": "missing result"}],
    [{"role": "assistant", "content": None, "tool_calls": [call()]},
     {"role": "tool", "tool_call_id": "other", "content": "wrong linkage"}],
    [{"role": "assistant", "content": None, "tool_calls": [call("a"), call("b")]},
     {"role": "tool", "tool_call_id": "b", "content": "unordered"}],
])
def test_native_missing_or_orphan_results_cannot_send_or_project(history):
    model = model_for(lambda request: pytest.fail("must not send HTTP"))
    with pytest.raises(ProtocolError):
        model.request(history, "policy")
    with pytest.raises(ProtocolError):
        project_context({}, history, [], protocol="nebius")


def test_duplicate_call_id_across_turns_rejected_before_second_effect(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        args = {"path": "a.py"} if len(requests) == 1 else {
            "path": "a.py", "expected_digest": digest_bytes(b"old"), "old": "old", "new": "new"}
        return httpx.Response(200, json=response([call("same", "read_file" if len(requests) == 1
                                                      else "replace_text", args)]))

    with pytest.raises(ProtocolError, match="duplicate tool ID across history"):
        harness_for(store, artifacts).run(owner, task["contract"], workspace, model_for(handler))
    state = store.snapshot("tenant", task["task_id"])
    assert len(requests) == 2 and len(state["dispatches"]) == 3  # two bills, only first tool
    assert state["budget"]["spent"] == 4 and workspace.snapshot() == {"a.py": "old"}


@pytest.mark.parametrize("prompt_details,completion_details", [
    (None, None),
    ({"cached_tokens": None}, {"reasoning_tokens": None}),
    ({"cached_tokens": None, "audio_tokens": None},
     {"reasoning_tokens": None, "audio_tokens": None, "accepted_prediction_tokens": None}),
    ({"cached_tokens": 30, "audio_tokens": None}, {"reasoning_tokens": 12, "audio_tokens": None}),
])
def test_nullable_schema_native_continuation_terminal_billing_and_replay(
        tmp_path, prompt_details, completion_details):
    rate = rates(input_per_million=100000)
    store, artifacts, task, owner, workspace = setup(tmp_path, rate=rate)
    counters = usage(prompt_tokens_details=prompt_details, completion_tokens_details=completion_details)
    first, terminal = response([call()], counters=counters), response(counters=counters)
    first["choices"][0]["message"]["reasoning_content"] = None
    terminal["choices"][0]["message"]["tool_calls"] = None
    bodies = [json.dumps(raw, indent=2).encode() for raw in (first, terminal)]
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        index = len(requests)
        requests.append(payload)
        if index:
            assert payload["messages"][2] == first["choices"][0]["message"]
            assert payload["messages"][3]["tool_call_id"] == "read"
        return httpx.Response(200, content=bodies[index])

    model = model_for(handler)
    harness = Harness(store, artifacts, provider_envelopes={MODEL: rate})
    result = harness.run(owner, task["contract"], workspace, model)
    assert harness.run(owner, task["contract"], workspace, model) == result
    assert len(requests) == 2
    assert result["messages"][-1] == terminal["choices"][0]["message"]
    assert result["messages"][-1]["tool_calls"] is None
    validate_nebius_linkage(result["messages"])
    normalized = parse_nebius_usage({"usage": counters})
    cached = 30 if isinstance(prompt_details, dict) and prompt_details.get("cached_tokens") == 30 else 0
    assert normalized == {"input_tokens": 100 - cached, "cache_read_input_tokens": cached, "output_tokens": 20}
    expected_charge = 8 if cached else 11
    state = store.snapshot("tenant", task["task_id"])
    assert state["budget"]["spent"] == 2 * expected_charge
    assert all(d["billing_state"] == "settled" for d in state["dispatches"])
    for index, item in enumerate(result["evidence"]):
        assert artifacts.get("tenant", task["task_id"], item["response_ref"]["digest"]) == bodies[index]
    # A caller may continue a previously terminal native message unchanged.
    continued = model.build_request(result["messages"] + [{"role": "user", "content": "follow up"}], "policy")
    assert continued["messages"][-2]["tool_calls"] is None


@pytest.mark.parametrize("field,details", [
    ("prompt_tokens_details", {"cached_tokens": -1}),
    ("prompt_tokens_details", {"cached_tokens": 101}),
    ("prompt_tokens_details", {"cached_tokens": True}),
    ("prompt_tokens_details", {"cached_tokens": None, "audio_tokens": -1}),
    ("completion_tokens_details", {"reasoning_tokens": -1}),
    ("completion_tokens_details", {"reasoning_tokens": 21}),
    ("completion_tokens_details", {"reasoning_tokens": None, "audio_tokens": 2**63}),
    ("completion_tokens_details", {"reasoning_tokens": None, "audio_tokens": False}),
    ("prompt_tokens_details", []),
    ("completion_tokens_details", "invalid"),
])
def test_nullable_details_still_reject_malformed_non_null_counters(field, details):
    with pytest.raises(ProtocolError):
        parse_nebius_usage({"usage": usage(**{field: details})})


def test_null_tool_calls_with_tool_finish_settles_usage_without_effects(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    raw = response(reason="tool_calls")
    raw["choices"][0]["message"]["tool_calls"] = None
    raw["usage"]["prompt_tokens_details"] = None
    raw["usage"]["completion_tokens_details"] = {"reasoning_tokens": None}
    body = json.dumps(raw).encode()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=body)

    model, harness = model_for(handler), harness_for(store, artifacts)
    for _ in range(2):
        with pytest.raises(ProtocolError, match="finish state"):
            harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(requests) == len(state["dispatches"]) == 1
    dispatch = state["dispatches"][0]
    assert dispatch["billing_state"] == "settled" and dispatch["actual_units"] == 2
    assert artifacts.get("tenant", task["task_id"], dispatch["result_ref"]["digest"]) == body
    assert workspace.snapshot() == {"a.py": "old"}


def test_nebius_cache_premium_envelope_rejected_before_dispatch_and_anthropic_unchanged(tmp_path):
    rate = rates(cache_read_per_million=10001)
    store, artifacts, task, owner, workspace = setup(tmp_path, rate=rate)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"type": "message", "role": "assistant", "model": MODEL, "content": [],
                                         "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 12, "output_tokens": 8}})

    harness = Harness(store, artifacts, provider_envelopes={MODEL: rate})
    with pytest.raises(PermissionError, match="cache premium"):
        harness.run(owner, task["contract"], workspace, model_for(handler))
    assert not requests and not store.snapshot("tenant", task["task_id"])["dispatches"]
    anthropic = AnthropicMessages("mock-only", MODEL, enable_network=True,
                                 client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = harness.run(owner, task["contract"], workspace, anthropic)
    assert result["status"] == "completion_proposed" and len(requests) == 1
