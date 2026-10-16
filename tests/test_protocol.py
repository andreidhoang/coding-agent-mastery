import httpx
import pytest

from service.context import project_context
from service.protocol import ProtocolError, SSEDecoder, ToolCall, ToolStream, strict_json, validate_linkage
from service.providers import AnthropicMessages, parse_anthropic_response


def test_sse_at_every_byte_boundary_preserves_unicode():
    raw = 'event: tool\r\ndata: {"text":"Việt Nam 🧠"}\r\n\r\n'.encode()
    expected = [{"event": "tool", "data": '{"text":"Việt Nam 🧠"}'}]
    for split in range(len(raw) + 1):
        parser = SSEDecoder()
        assert parser.feed(raw[:split]) + parser.feed(raw[split:], final=True) == expected
    parser = SSEDecoder()
    output = []
    for byte in raw:
        output += parser.feed(bytes([byte]))
    output += parser.feed(b"", final=True)
    assert output == expected


def test_incomplete_arguments_never_emit_a_call():
    assembler = ToolStream()
    assembler.start("c1", "read_file")
    assembler.delta("c1", '{"path":"x')
    assert assembler.complete == {}
    with pytest.raises(ProtocolError):
        assembler.end()
    assert assembler.complete == {}


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}',
                                '1e999', '-1e999', '{"x":[0,{"y":1e999}]}',
                                "[" * 30 + "0" + "]" * 30])
def test_ambiguous_json_rejected(raw):
    with pytest.raises(ProtocolError):
        strict_json(raw)


def test_unknown_tools_extra_fields_duplicate_completion():
    with pytest.raises(ProtocolError):
        ToolCall("id", "read_secrets", {})
    with pytest.raises(ProtocolError):
        ToolCall("id", "read_file", {"path": "a", "tenant_id": "victim"})
    assembler = ToolStream()
    assembler.start("c", "read_file")
    assembler.delta("c", '{"path":"a"}')
    assert assembler.finish("c").arguments == {"path": "a"}
    with pytest.raises(ProtocolError):
        assembler.finish("c")


def test_tool_pairing_cannot_be_spliced_or_summarized():
    use = {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "c", "name": "read_file", "input": {"path": "a"}}],
    }
    result = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c", "content": "value"}]}
    validate_linkage([use, result])
    with pytest.raises(ProtocolError):
        validate_linkage([use, {"role": "assistant", "content": "done"}])
    with pytest.raises(ProtocolError):
        validate_linkage([result])
    with pytest.raises(ValueError, match="context byte budget"):
        project_context({"requirements": "must preserve"}, [use, result], [], max_bytes=20)


def test_adapter_preserves_opaque_content_and_has_no_implicit_retry():
    opaque = {"type": "thinking", "thinking": "opaque test fixture", "signature": "opaque-signature"}
    raw = {
        "type": "message",
        "role": "assistant",
        "model": "explicit-model-id",
        "content": [opaque],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 2, "output_tokens": 3},
    }
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=raw)

    adapter = AnthropicMessages(
        "test-only",
        "explicit-model-id",
        enable_network=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    payload, response = adapter.request([{"role": "user", "content": "hello"}], "policy")
    assert response.raw["content"][0] == opaque
    assert response.usage["output_tokens"] == 3
    assert len(requests) == 1
    assert payload["model"] == "explicit-model-id"
    raw["stop_reason"] = "max_tokens"
    with pytest.raises(ProtocolError):
        parse_anthropic_response(raw)


def test_live_transport_is_disabled_by_default():
    adapter = AnthropicMessages("test-only", "explicit-model-id")
    with pytest.raises(PermissionError):
        adapter.request([], "policy")
