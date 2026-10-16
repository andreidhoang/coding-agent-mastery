import copy

import pytest

from service.artifacts import digest_json
from service.context import default_context_config, plan_context
from service.protocol import ToolCall, tool_schemas
from service.providers import AnthropicMessages, NebiusChatCompletions, ScriptedModel, context_capability


def fixture(protocol="anthropic", provider="scripted"):
    contract = {"capabilities": ["read_context_artifact"]}
    messages = []
    for i in range(3):
        if protocol == "anthropic":
            messages.extend([{"role": "assistant", "content": [
                {"type": "thinking", "thinking": "opaque", "signature": "signed"},
                {"type": "tool_use", "id": str(i), "name": "read_file", "input": {"path": "a"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": str(i),
                                               "content": "sentinel" * 800, "is_error": False}]}])
        else:
            messages.extend([{"role": "assistant", "content": None, "reasoning_content": "opaque",
                              "tool_calls": [{"id": str(i), "type": "function", "function": {
                                  "name": "read_file", "arguments": '{"path":"a"}'}}]},
                             {"role": "tool", "tool_call_id": str(i), "content": "sentinel" * 800}])
    config = default_context_config(100000, "tool_result_offload_v1")
    binding = {"tenant_id": "t", "task_id": "x", "generation": 1, "owner": {"service_incarnation": "i", "tenant_id": "t", "task_id": "x",
                         "generation": 1, "node_id": "n", "node_epoch": 1, "attempt_id": "a"},
               "contract_digest": digest_json(contract), "source_history_digest": digest_json(messages),
               "source_evidence_digest": digest_json([]), "source_workspace_digest": digest_json({}),
               "source_frontier": {"service_incarnation": "i", "sequence": 0},
               "expected_previous_projection_id": None, "config_digest": digest_json(config),
               "adapter": {"provider": provider, "protocol": protocol, "adapter_version": "context_v1",
                           "model": "m", "endpoint": None, "system_digest": digest_json(""),
                           "tools_digest": digest_json(tool_schemas(include_context=True)),
                           "continuation_capability": "scripted_tool_result_offload_v1" if protocol == "anthropic"
                           else "nebius_chat_completions_tool_result_offload_v1"}}
    return contract, messages, config, binding


@pytest.mark.parametrize("protocol,provider", [("anthropic", "scripted"), ("nebius", "nebius")])
def test_deterministic_preserves_opaque_tail_and_sources(protocol, provider):
    contract, messages, config, binding = fixture(protocol, provider)
    config["max_bytes"] = 11000
    binding["config_digest"] = digest_json(config)
    original = copy.deepcopy(messages)
    first = plan_context(contract, messages, [], binding=binding, config=config, protocol=protocol)
    assert first == plan_context(contract, messages, [], binding=binding, config=config, protocol=protocol)
    assert messages == original
    assert first["projection"]["messages"][-2:] == messages[-2:]
    assert first["projection"]["messages"][0] == messages[0]
    assert [entry["call_id"] for entry in first["offloads"]] == ["0", "1"]
    assert first["digest"] == digest_json(first["projection"])
    assert first["token_count"] is None


def test_full_fit_and_refusals():
    contract, messages, config, binding = fixture()
    assert not plan_context(contract, messages, [], binding=binding, config=config,
                            protocol="anthropic")["offloads"]
    for mutate in (lambda: contract["capabilities"].clear(),
                   lambda: binding["adapter"].update(provider="anthropic")):
        contract, messages, config, binding = fixture()
        mutate()
        binding["contract_digest"] = digest_json(contract)
        with pytest.raises(ValueError):
            plan_context(contract, messages, [], binding=binding, config=config, protocol="anthropic")
    config["max_bytes"] = 1
    binding["config_digest"] = digest_json(config)
    with pytest.raises(ValueError):
        plan_context(contract, messages, [], binding=binding, config=config, protocol="anthropic")


@pytest.mark.parametrize("field", ["schema", "max_bytes", "min_offload_bytes", "keep_recent_tool_batches",
                                   "retrieval_max_bytes"])
def test_boolean_not_integer(field):
    contract, messages, config, binding = fixture()
    config[field] = True
    with pytest.raises(ValueError):
        plan_context(contract, messages, [], binding=binding, config=config, protocol="anthropic")


def test_schema_defaults_and_explicit_capability():
    assert len(tool_schemas()) == 5
    schema = tool_schemas(include_context=True)[-1]
    assert schema["input_schema"]["properties"]["offset"] == {"type": "integer"}
    with pytest.raises(ValueError):
        ToolCall("x", "read_context_artifact", {"digest": "a", "offset": True, "limit": 1})
    assert context_capability(ScriptedModel([])) == "scripted_tool_result_offload_v1"
    assert context_capability(AnthropicMessages("k", "m")) == "anthropic_full_history_v1"
    adapter = NebiusChatCompletions("k", "m")
    assert len(adapter.build_request([], "") ["tools"]) == 5
    assert len(adapter.build_request([], "", include_context=True)["tools"]) == 6


def test_threshold_recent_batches_and_retrieval_results_protected():
    contract, messages, config, binding = fixture()
    messages[0]["content"][1]["name"] = "read_context_artifact"
    messages[0]["content"][1]["input"] = {"digest": "a" * 64, "offset": 0, "limit": 1}
    messages[2]["content"].append({"type": "tool_use", "id": "extra", "name": "read_file",
                                    "input": {"path": "b"}})
    messages[3]["content"].append({"type": "tool_result", "tool_use_id": "extra", "content": "x" * 1024})
    config["max_bytes"] = 17000
    binding["config_digest"] = digest_json(config)
    binding["source_history_digest"] = digest_json(messages)
    result = plan_context(contract, messages, [], binding=binding, config=config, protocol="anthropic")
    assert [d["call_id"] for d in result["offloads"]] == ["1"]
    assert result["projection"]["messages"][3]["content"][1]["content"] == "x" * 1024
    assert result["projection"]["messages"][1] == messages[1]
    assert result["projection"]["messages"][2] == messages[2]


def test_nebius_receive_exact_opt_in_and_tamper_rejection():
    import httpx

    captured = []

    def handler(request):
        import json
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=b"{}")

    adapter = NebiusChatCompletions("k", "m", enable_network=True,
                                    client=httpx.Client(transport=httpx.MockTransport(handler)))
    payload = adapter.build_request([], "s", include_context=True)
    assert adapter.receive(payload) == b"{}"
    assert captured == [payload]
    tampered = copy.deepcopy(payload)
    tampered["tools"][-1]["function"]["parameters"]["properties"]["offset"]["type"] = "string"
    with pytest.raises(ValueError):
        adapter.receive(tampered)
    assert len(captured) == 1


@pytest.mark.parametrize("mutation", [
    lambda b: b["owner"].update(extra="bad"),
    lambda b: b["owner"].update(node_epoch=True),
    lambda b: b.update(generation=True),
    lambda b: b["source_frontier"].update(sequence=True),
    lambda b: b["source_frontier"].update(service_incarnation="other"),
    lambda b: b.update(source_workspace_digest="bad"),
    lambda b: b.update(expected_previous_projection_id="bad"),
    lambda b: b["adapter"].update(tools_digest="bad"),
])
def test_malformed_binding_refused(mutation):
    contract, messages, config, binding = fixture()
    mutation(binding)
    with pytest.raises((ValueError, RuntimeError)):
        plan_context(contract, messages, [], binding=binding, config=config, protocol="anthropic")


@pytest.mark.parametrize("include_context", [False, True])
def test_nebius_rejects_boolean_integer_schema_alias_before_transport(include_context):
    import httpx

    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, content=b"{}")

    adapter = NebiusChatCompletions("k", "m", enable_network=True,
                                    client=httpx.Client(transport=httpx.MockTransport(handler)))
    expected = adapter.build_request([], "s", include_context=include_context)
    payload = copy.deepcopy(expected)
    payload["tools"][-1]["function"]["parameters"]["additionalProperties"] = 0
    assert payload == expected  # Python aliases bool and int; wire JSON does not.
    with pytest.raises(ValueError, match="unsupported native request envelope"):
        adapter.receive(payload)
    assert not captured


def test_legacy_nebius_override_keeps_approval_checks():
    import httpx

    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, content=b"{}")

    class LegacyApproved(NebiusChatCompletions):
        def build_request(self, messages, system, max_tokens=1024):
            if system != "approved":
                raise PermissionError("approval mismatch")
            return super().build_request(messages, system, max_tokens)

    adapter = LegacyApproved("k", "m", enable_network=True,
                              client=httpx.Client(transport=httpx.MockTransport(handler)))
    payload = adapter.build_request([], "approved")
    assert adapter.receive(payload) == b"{}"
    payload["messages"][0]["content"] = "unapproved"
    with pytest.raises(PermissionError, match="approval mismatch"):
        adapter.receive(payload)
    opt_in = NebiusChatCompletions.build_request(adapter, [], "approved", include_context=True)
    with pytest.raises(TypeError, match="include_context"):
        adapter.receive(opt_in)
    assert len(captured) == 1
