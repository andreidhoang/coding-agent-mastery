"""Wire framing and complete tool envelopes; stream deltas never authorize effects."""

from __future__ import annotations

import codecs
import json
import math
from dataclasses import dataclass
from typing import Any

from .artifacts import digest_json


class ProtocolError(ValueError):
    pass


def strict_json(text: str, max_bytes: int = 65536) -> Any:
    if len(text.encode()) > max_bytes:
        raise ProtocolError("JSON byte limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProtocolError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ProtocolError(f"nonfinite JSON number: {value}")

    try:
        value = json.loads(text, object_pairs_hook=unique, parse_constant=invalid)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError("invalid complete JSON") from exc

    def depth(item, level=0):
        if level > 24:
            raise ProtocolError("JSON nesting limit")
        if isinstance(item, float) and not math.isfinite(item):
            # parse_constant rejects NaN/Infinity tokens, but exponent overflow
            # such as 1e999 reaches us as a float without calling that hook.
            raise ProtocolError("nonfinite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                depth(child, level + 1)
        elif isinstance(item, list):
            for child in item:
                depth(child, level + 1)

    depth(value)
    return value


class SSEDecoder:
    """Incremental UTF-8, LF/CRLF framing; incomplete final events are rejected."""

    def __init__(self, max_event_bytes: int = 262144):
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.buffer = ""
        self.max_bytes = max_event_bytes

    def feed(self, data: bytes, final: bool = False) -> list[dict]:
        try:
            self.buffer += self.decoder.decode(data, final=final)
        except UnicodeError as exc:
            raise ProtocolError("invalid or truncated UTF-8") from exc
        self.buffer = self.buffer.replace("\r\n", "\n")
        result = []
        while "\n\n" in self.buffer:
            frame, self.buffer = self.buffer.split("\n\n", 1)
            if len(frame.encode()) > self.max_bytes:
                raise ProtocolError("SSE frame byte limit")
            fields: dict[str, Any] = {"event": "message", "data": []}
            for line in frame.split("\n"):
                if not line or line.startswith(":"):
                    continue
                name, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if name == "data":
                    fields["data"].append(value)
                elif name in {"event", "id"}:
                    fields[name] = value
            if fields["data"]:
                fields["data"] = "\n".join(fields["data"])
                result.append(fields)
        if len(self.buffer.encode()) > self.max_bytes:
            raise ProtocolError("SSE buffer byte limit")
        if final and self.buffer.strip():
            raise ProtocolError("stream ended inside SSE frame")
        return result


TOOL_FIELDS = {
    "read_file": {"path": str},
    "search": {"query": str},
    "replace_text": {"path": str, "expected_digest": str, "old": str, "new": str},
    "run_tests": {},
    "finish": {"summary": str},
    "read_context_artifact": {"digest": str, "offset": int, "limit": int},
    "load_skill": {"catalog_digest": str, "package_digest": str},
    "read_skill_resource": {"catalog_digest": str, "package_digest": str,
                            "path": str, "offset": int, "limit": int},
}


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict

    def __post_init__(self):
        if not isinstance(self.call_id, str) or not 1 <= len(self.call_id) <= 160:
            raise ProtocolError("invalid tool call ID")
        if self.name not in TOOL_FIELDS or not isinstance(self.arguments, dict):
            raise ProtocolError("unknown tool or arguments type")
        expected = TOOL_FIELDS[self.name]
        if set(self.arguments) != set(expected):
            raise ProtocolError("tool fields must exactly match schema")
        for key, kind in expected.items():
            if type(self.arguments[key]) is not kind:
                raise ProtocolError(f"incorrect type for {key}")
        if len(json.dumps(self.arguments).encode()) > 65536:
            raise ProtocolError("tool arguments too large")

    @property
    def digest(self) -> str:
        return digest_json(
            {"schema": 1, "call_id": self.call_id, "name": self.name, "arguments": self.arguments}
        )


def tool_schemas(*, include_context: bool = False, include_skills: bool = False) -> list[dict]:
    if type(include_context) is not bool or type(include_skills) is not bool:
        raise ValueError("tool schema options must be boolean")
    return [
        {
            "name": name,
            "description": f"Bounded workspace operation: {name}",
            "input_schema": {
                "type": "object",
                "properties": {key: {"type": "integer" if kind is int else "string"}
                               for key, kind in fields.items()},
                "required": list(fields),
                "additionalProperties": False,
            },
        }
        for name, fields in TOOL_FIELDS.items()
        if (include_context or name != "read_context_artifact")
        and (include_skills or name not in {"load_skill", "read_skill_resource"})
    ]


class ToolStream:
    """Normalized adapter state machine. Persist emitted calls before admitting them."""

    def __init__(self):
        self.pending: dict[str, dict] = {}
        self.complete: dict[str, ToolCall] = {}
        self.ended = False

    def start(self, call_id: str, name: str):
        if self.ended or call_id in self.pending or call_id in self.complete:
            raise ProtocolError("duplicate start or ended stream")
        if name not in TOOL_FIELDS:
            raise ProtocolError("unknown tool")
        self.pending[call_id] = {"name": name, "text": ""}

    def delta(self, call_id: str, text: str):
        if self.ended or call_id not in self.pending:
            raise ProtocolError("delta has no open call")
        self.pending[call_id]["text"] += text
        if len(self.pending[call_id]["text"].encode()) > 65536:
            raise ProtocolError("tool delta limit")

    def finish(self, call_id: str) -> ToolCall:
        if call_id not in self.pending:
            raise ProtocolError("completion has no pending call")
        item = self.pending.pop(call_id)
        call = ToolCall(call_id, item["name"], strict_json(item["text"]))
        self.complete[call_id] = call
        return call

    def end(self):
        self.ended = True
        if self.pending:
            raise ProtocolError("incomplete tool calls at response end")


def validate_linkage(messages: list[dict]) -> None:
    pending: set[str] = set()
    used: set[str] = set()
    for message in messages:
        if pending and message.get("role") != "user":
            raise ProtocolError("assistant continued before tool results")
        content = message.get("content", [])
        if isinstance(content, str):
            if pending:
                raise ProtocolError("missing tool result before continuation")
            continue
        for block in content:
            if block.get("type") == "tool_use":
                if message.get("role") != "assistant" or block["id"] in used:
                    raise ProtocolError("duplicate or misplaced tool use")
                pending.add(block["id"])
                used.add(block["id"])
            elif block.get("type") == "tool_result":
                if message.get("role") != "user" or block["tool_use_id"] not in pending:
                    raise ProtocolError("orphan or duplicate tool result")
                pending.remove(block["tool_use_id"])
            elif pending and message.get("role") != "assistant":
                raise ProtocolError("tool results must precede other user content")
    if pending:
        raise ProtocolError("missing tool results")


def nebius_tool_calls(message: dict) -> tuple[ToolCall, ...]:
    """Validate complete native Chat Completions function calls, keeping opaque fields."""
    blocks = message.get("tool_calls")
    # The native schema permits null when no tool calls are present. Keep the
    # original field in the message; only the validated proposal is empty.
    if blocks is None:
        return ()
    if not isinstance(blocks, list):
        raise ProtocolError("tool_calls must be a list")
    calls, seen = [], set()
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "function":
            raise ProtocolError("unsupported tool call type")
        function = block.get("function")
        if (not isinstance(function, dict) or not isinstance(function.get("arguments"), str)
                or not isinstance(function.get("name"), str)):
            raise ProtocolError("function arguments must be complete JSON text")
        call = ToolCall(block.get("id"), function.get("name"), strict_json(function["arguments"]))
        if call.call_id in seen:
            raise ProtocolError("duplicate tool ID")
        seen.add(call.call_id)
        calls.append(call)
    return tuple(calls)


def validate_nebius_linkage(messages: list[dict]) -> None:
    """Require ordered, unique native tool results before any continuation."""
    if not isinstance(messages, list):
        raise ProtocolError("messages must be a list")
    pending: list[str] = []
    used: set[str] = set()
    for message in messages:
        if not isinstance(message, dict):
            raise ProtocolError("invalid native message")
        role = message.get("role")
        if not isinstance(role, str) or role not in {"system", "user", "assistant", "tool"}:
            raise ProtocolError("unsupported native message role")
        if pending and role != "tool":
            raise ProtocolError("assistant continued before tool results")
        if role == "tool":
            if not pending or message.get("tool_call_id") != pending[0]:
                raise ProtocolError("orphan, duplicate or unordered tool result")
            if not isinstance(message.get("content"), str) or "tool_calls" in message:
                raise ProtocolError("invalid native tool result")
            pending.pop(0)
        elif role == "assistant":
            if message.get("content") is not None and not isinstance(message.get("content"), str):
                raise ProtocolError("unsupported assistant content")
            for call in nebius_tool_calls(message):
                if call.call_id in used:
                    raise ProtocolError("duplicate tool ID across history")
                used.add(call.call_id)
                pending.append(call.call_id)
        elif not isinstance(message.get("content"), str) or "tool_calls" in message:
            raise ProtocolError("invalid native user/system message")
    if pending:
        raise ProtocolError("missing tool results")
