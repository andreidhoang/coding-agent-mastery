"""Provider transport is outside authority transactions and never retries implicitly."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from .artifacts import canonical_bytes, digest_json
from .protocol import (
    ProtocolError, ToolCall, nebius_tool_calls, strict_json, tool_schemas,
    validate_linkage, validate_nebius_linkage,
)


@dataclass(frozen=True)
class ModelResponse:
    raw: dict
    calls: tuple[ToolCall, ...]
    usage: dict
    terminal: bool


def decode_provider_payload(body: bytes, max_bytes: int = 2_000_000) -> Any:
    """Decode a retained complete entity body without authorizing its content."""
    try:
        text = body.decode("utf-8")
    except UnicodeError as error:
        raise ProtocolError("provider response is not complete UTF-8") from error
    return strict_json(text, max_bytes)


def decode_anthropic_payload(body: bytes, max_bytes: int = 2_000_000) -> Any:
    return decode_provider_payload(body, max_bytes)


def parse_anthropic_usage(raw: Any) -> dict:
    """Validate billing counters independently of tool/terminal semantics.

    Counts come from a complete authenticated-provider response, not model text.
    Missing/untrusted counters cannot release conservative billing exposure.
    Preserve additional provider fields unchanged alongside the raw receipt.
    """
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if not isinstance(usage, dict):
        raise ProtocolError("missing provider usage receipt")
    required = ("input_tokens", "output_tokens")
    optional = ("cache_read_input_tokens", "cache_creation_input_tokens")
    for name in required + tuple(name for name in optional if name in usage):
        if type(usage.get(name)) is not int or not 0 <= usage[name] <= 2**63 - 1:
            raise ProtocolError("invalid usage receipt")
    return usage


def parse_anthropic_response(raw: dict, expected_model: str | None = None) -> ModelResponse:
    if not isinstance(raw, dict):
        raise ProtocolError("unsupported message envelope")
    if raw.get("type") != "message" or raw.get("role") != "assistant":
        raise ProtocolError("unsupported message envelope")
    if expected_model is not None and raw.get("model") != expected_model:
        raise ProtocolError("provider model identity mismatch")
    reason = raw.get("stop_reason")
    if reason not in {"tool_use", "end_turn", "stop_sequence"}:
        raise ProtocolError("incomplete or unsupported finish state")
    content = raw.get("content")
    if not isinstance(content, list):
        raise ProtocolError("message content must be a list")
    calls = []
    seen = set()
    for block in content:
        if not isinstance(block, dict):
            raise ProtocolError("invalid content block")
        if block.get("type") == "tool_use":
            call = ToolCall(block.get("id"), block.get("name"), block.get("input"))
            if call.call_id in seen:
                raise ProtocolError("duplicate tool ID")
            seen.add(call.call_id)
            calls.append(call)
        # Thinking signatures and other opaque blocks remain unchanged in raw.
    if bool(calls) != (reason == "tool_use"):
        raise ProtocolError("stop reason and tool blocks disagree")
    usage = parse_anthropic_usage(raw)
    return ModelResponse(raw, tuple(calls), usage, not calls)


class AnthropicMessages:
    """Explicit opt-in gateway. Caller must reserve conservative billing exposure first.

    Raw request/response bytes must be stored by the caller. No provider/model alias is
    selected here: model identity, output bound and prices belong to the frozen run.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        enable_network: bool = False,
        client: httpx.Client | None = None,
        max_response_bytes: int = 2_000_000,
    ):
        if not model or not api_key:
            raise ValueError("explicit provider model and server-held key required")
        self.model, self.key = model, api_key
        self.enabled, self.max_bytes = enable_network, max_response_bytes
        self.client = client or httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=False)

    def build_request(
        self, messages: list[dict], system: str, max_tokens: int = 1024,
        *, include_context: bool = False,
    ) -> dict:
        if type(max_tokens) is not int or not 1 <= max_tokens <= 32768:
            raise ValueError("invalid output cap")
        validate_linkage(messages)
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "tools": tool_schemas(include_context=include_context),
            "stream": False,
        }

    def receive(self, payload: dict) -> bytes:
        """Return the complete bounded entity body before semantic validation.

        The gateway caller persists these exact bytes before decoding message
        semantics or billing. A partial/failed transport remains unresolved.
        """
        if not self.enabled:
            raise PermissionError("live provider access is disabled")
        if payload.get("model") != self.model:
            raise ValueError("frozen provider model identity mismatch")
        with self.client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self.max_bytes:
                    raise ProtocolError("provider response byte bound exceeded")
                chunks.append(chunk)
        return b"".join(chunks)

    def complete(self, payload: dict) -> ModelResponse:
        """Convenience parsing; durable gateways use receive then persist first."""
        return parse_anthropic_response(
            decode_anthropic_payload(self.receive(payload), self.max_bytes), self.model
        )

    def request(
        self, messages: list[dict], system: str, max_tokens: int = 1024
    ) -> tuple[dict, ModelResponse]:
        payload = self.build_request(messages, system, max_tokens)
        return payload, self.complete(payload)


class ScriptedModel:
    """Deterministic mechanics fixture; it makes no learned coding-capability claim."""

    def __init__(self, turns: list[list[ToolCall]]):
        self.turns = turns

    def response(self, turn: int) -> ModelResponse:
        if turn >= len(self.turns):
            calls = []
        else:
            calls = self.turns[turn]
        raw: dict[str, Any] = {
            "type": "message",
            "role": "assistant",
            "model": "scripted-fixture-v1",
            "content": [
                {"type": "tool_use", "id": c.call_id, "name": c.name, "input": c.arguments} for c in calls
            ],
            "stop_reason": "tool_use" if calls else "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        return parse_anthropic_response(raw)


def parse_nebius_usage(raw: Any) -> dict:
    """Normalize subset counters into the existing disjoint billing categories."""
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if not isinstance(usage, dict):
        raise ProtocolError("missing provider usage receipt")

    def count(value):
        if type(value) is not int or not 0 <= value <= 2**63 - 1:
            raise ProtocolError("invalid usage receipt")
        return value

    prompt, output = count(usage.get("prompt_tokens")), count(usage.get("completion_tokens"))
    if "total_tokens" in usage and count(usage["total_tokens"]) != prompt + output:
        raise ProtocolError("inconsistent total usage")
    cached = 0
    for field, subset, limit in (
        ("prompt_tokens_details", "cached_tokens", prompt),
        ("completion_tokens_details", "reasoning_tokens", output),
    ):
        if usage.get(field) is None:
            continue
        details = usage[field]
        if not isinstance(details, dict):
            raise ProtocolError("invalid usage details")
        # Other detail counters, when supplied, are also bounded nonnegative
        # integers. Their provider meaning stays in the immutable raw receipt.
        for value in details.values():
            if value is not None:
                count(value)
        # A null/missing breakdown is no evidence of cached discount or extra
        # reasoning. Bill all unknown prompt tokens at the approved input rate.
        value = details.get(subset)
        if value is None:
            value = 0
        if value > limit:
            raise ProtocolError("usage subset exceeds total")
        if subset == "cached_tokens":
            cached = value
    return {"input_tokens": prompt - cached, "cache_read_input_tokens": cached, "output_tokens": output}


def parse_nebius_response(raw: Any, model: str) -> ModelResponse:
    """Accept only one complete native assistant choice for the pinned identity."""
    if not isinstance(raw, dict) or raw.get("object") != "chat.completion":
        raise ProtocolError("unsupported completion envelope")
    if raw.get("model") != model:
        raise ProtocolError("provider model identity mismatch")
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ProtocolError("exactly one completion choice required")
    choice = choices[0]
    if not isinstance(choice, dict) or type(choice.get("index")) is not int or choice["index"] != 0:
        raise ProtocolError("invalid completion choice index")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ProtocolError("unsupported assistant envelope")
    if message.get("content") is not None and not isinstance(message.get("content"), str):
        raise ProtocolError("unsupported assistant content")
    calls = nebius_tool_calls(message)
    reason = choice.get("finish_reason")
    if (not isinstance(reason, str) or reason not in {"tool_calls", "stop"}
            or bool(calls) != (reason == "tool_calls")):
        raise ProtocolError("incomplete or unsupported finish state")
    return ModelResponse(raw, calls, parse_nebius_usage(raw), not calls)


NEBIUS_ERROR_CONTENT_TYPE = "application/vnd.coding-agent.provider-transport-error+json"
_NEBIUS_ERROR_HEADERS = (
    "x-request-id", "request-id", "retry-after", "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests", "x-ratelimit-reset-requests", "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens", "ratelimit-limit",
    "ratelimit-remaining", "ratelimit-reset",
)
_NEBIUS_ERROR_FIELDS = frozenset({
    "schema", "kind", "provider", "protocol", "endpoint", "method", "path", "model",
    "payload_digest", "request_started_at", "observed_at", "status_code", "headers",
    "headers_limited", "body_base64", "captured_bytes", "retained_bytes", "body_complete",
    "body_truncated", "body_redacted", "read_error",
})


def _has_controls(value: str) -> bool:
    return any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)


def _validate_nebius_error(payload: dict) -> bytes:
    """Validate a closed diagnostic schema, then freeze its canonical bytes."""
    invalid = "invalid Nebius HTTP diagnostic"
    if not isinstance(payload, dict) or set(payload) != _NEBIUS_ERROR_FIELDS:
        raise ValueError(invalid)
    for name, expected in {
        "schema": 1, "kind": "nebius_http_error", "provider": "nebius",
        "protocol": "chat_completions", "endpoint": NebiusChatCompletions.ENDPOINT,
        "method": "POST", "path": "chat/completions",
    }.items():
        if type(payload[name]) is not type(expected) or payload[name] != expected:
            raise ValueError(invalid)
    if not isinstance(payload["model"], str) or not payload["model"].strip():
        raise ValueError(invalid)
    if not isinstance(payload["payload_digest"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", payload["payload_digest"]
    ):
        raise ValueError(invalid)
    for name in ("request_started_at", "observed_at"):
        try:
            if not isinstance(payload[name], str):
                raise ValueError(invalid)
            stamp = datetime.fromisoformat(payload[name])
            if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError(invalid)
        except (ValueError, OverflowError):
            raise ValueError(invalid) from None
    status = payload["status_code"]
    if type(status) is not int or not 100 <= status <= 599 or 200 <= status < 300:
        raise ValueError(invalid)
    for name in ("headers_limited", "body_complete", "body_truncated", "body_redacted"):
        if type(payload[name]) is not bool:
            raise ValueError(invalid)
    for name in ("captured_bytes", "retained_bytes"):
        if type(payload[name]) is not int or not 0 <= payload[name] <= 65536:
            raise ValueError(invalid)
    try:
        if not isinstance(payload["body_base64"], str) or len(payload["body_base64"]) > 87384:
            raise ValueError(invalid)
        body = base64.b64decode(payload["body_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError(invalid) from None
    read_error = payload["read_error"]
    if read_error is not None and not isinstance(read_error, str):
        raise ValueError(invalid)
    if (
        len(body) != payload["retained_bytes"]
        or payload["retained_bytes"] > payload["captured_bytes"]
        or (not payload["body_redacted"] and payload["retained_bytes"] != payload["captured_bytes"])
        or (payload["body_complete"] and payload["body_truncated"])
        or payload["read_error"] not in {None, "body_limit", "timeout", "read_error", "decode_error", "close_error"}
        or (payload["body_truncated"] and payload["read_error"] not in {"body_limit", "close_error"})
        or (payload["read_error"] == "body_limit" and not payload["body_truncated"])
        or (payload["body_complete"] and payload["read_error"] not in {None, "close_error"})
        or (not payload["body_complete"] and payload["read_error"] is None)
    ):
        raise ValueError(invalid)
    headers = payload["headers"]
    if not isinstance(headers, dict):
        raise ValueError(invalid)
    size = 0
    for name, values in headers.items():
        if name not in _NEBIUS_ERROR_HEADERS or not isinstance(values, list) or not 1 <= len(values) <= 2:
            raise ValueError(invalid)
        size += len(name.encode("utf-8"))
        for value in values:
            if not isinstance(value, str) or _has_controls(value) or len(value.encode("utf-8")) > 256:
                raise ValueError(invalid)
            size += len(value.encode("utf-8"))
    if size > 4096:
        raise ValueError(invalid)
    return canonical_bytes(payload)


class NebiusHTTPError(RuntimeError):
    """Sanitized observed HTTP failure; its body never grants completion authority."""

    def __init__(self, payload: dict):
        self._diagnostic_bytes = _validate_nebius_error(payload)
        super().__init__(f"Nebius HTTP error (status {payload['status_code']})")

    def __setattr__(self, name, value):
        if name == "_diagnostic_bytes" and hasattr(self, name):
            raise AttributeError("immutable Nebius HTTP diagnostic")
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if name == "_diagnostic_bytes":
            raise AttributeError("immutable Nebius HTTP diagnostic")
        super().__delattr__(name)

    @property
    def status_code(self) -> int:
        return self.as_dict()["status_code"]

    def as_dict(self) -> dict:
        return json.loads(self._diagnostic_bytes)

    def __str__(self) -> str:
        return f"Nebius HTTP error (status {self.status_code})"

    def __repr__(self) -> str:
        return f"NebiusHTTPError(status_code={self.status_code})"


class NebiusChatCompletions:
    """Global-only, explicit opt-in native adapter; model and rates have no defaults.

    max_tokens is the first-slice output field. Its live enforcement, including
    reasoning, must be established independently before a paid run is approved.
    Injected clients must use a no-retry transport; each receive dispatch sends
    once and explicitly disables redirects, even if the client enables them.
    """

    ENDPOINT = "https://api.tokenfactory.nebius.com/v1/"

    def __init__(
        self, api_key: str, model: str, *, endpoint: str = ENDPOINT,
        enable_network: bool = False, client: httpx.Client | None = None,
        max_response_bytes: int = 2_000_000,
    ):
        if not isinstance(model, str) or not model.strip() or not isinstance(api_key, str) or not api_key:
            raise ValueError("explicit provider model and server-held key required")
        if endpoint != self.ENDPOINT:
            raise ValueError("unapproved Nebius endpoint")
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 2_000_000:
            raise ValueError("invalid response byte bound")
        self.model, self.key, self.endpoint = model, api_key, endpoint
        self.enabled, self.max_bytes = enable_network, max_response_bytes
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(60, connect=10), follow_redirects=False,
            transport=httpx.HTTPTransport(retries=0),
        )

    def build_request(
        self, messages: list[dict], system: str, max_tokens: int = 1024,
        *, include_context: bool = False, include_skills: bool = False,
    ) -> dict:
        if type(max_tokens) is not int or not 1 <= max_tokens <= 32768:
            raise ValueError("invalid output cap")
        if not isinstance(system, str):
            raise ValueError("system instruction must be text")
        validate_nebius_linkage(messages)
        tools = [
            {"type": "function", "function": {
                "name": tool["name"], "description": tool["description"],
                "parameters": tool["input_schema"],
            }}
            for tool in tool_schemas(include_context=include_context, include_skills=include_skills)
        ]
        return {"model": self.model, "messages": [{"role": "system", "content": system}] + messages,
                "tools": tools, "tool_choice": "auto", "n": 1, "stream": False,
                "max_tokens": max_tokens}

    def _credential_patterns(self) -> tuple[bytes, ...]:
        # Include both JSON encodings of non-ASCII credentials, without quotes.
        return tuple(dict.fromkeys([
            self.key.encode("utf-8"),
            json.dumps(self.key, ensure_ascii=True)[1:-1].encode("utf-8"),
            json.dumps(self.key, ensure_ascii=False)[1:-1].encode("utf-8"),
        ]))

    def _error_headers(self, response: httpx.Response) -> tuple[dict, bool]:
        headers, limited, size = {}, False, 0
        patterns = self._credential_patterns()
        for raw_name, raw_value in response.headers.raw:
            try:
                name = raw_name.decode("ascii").lower()
            except UnicodeDecodeError:
                continue
            if name not in _NEBIUS_ERROR_HEADERS:
                continue
            value = raw_value.decode(response.headers.encoding)
            encoded = value.encode("utf-8")
            if (
                _has_controls(value) or any(pattern in encoded for pattern in patterns)
                or len(headers.get(name, [])) >= 2
            ):
                limited = True
                continue
            if len(encoded) > 256:
                value = encoded[:256].decode("utf-8", errors="ignore")
                encoded, limited = value.encode("utf-8"), True
            extra = len(encoded) + (len(name.encode("utf-8")) if name not in headers else 0)
            if size + extra > 4096:
                limited = True
                continue
            headers.setdefault(name, []).append(value)
            size += extra
        return headers, limited

    def _error_body(self, response: httpx.Response, diagnostic: dict) -> None:
        cap = min(self.max_bytes, 65536)
        prefix = bytearray()
        close_failed = False
        original_close = response.close

        def observe_close():
            nonlocal close_failed
            try:
                original_close()
            except Exception:
                # HTTPX iter_raw closes at raw EOF before decoded EOF/flush.
                # Let iter_bytes finish so actual entity completeness survives.
                close_failed = True

        response.close = observe_close
        try:
            # HTTPX buffers until chunk_size before yielding. A one-byte chunk
            # preserves every available byte even when the next read fails.
            for chunk in response.iter_bytes(chunk_size=1):
                if len(prefix) == cap:
                    diagnostic.update(body_truncated=True, read_error="body_limit")
                    break
                prefix.extend(chunk)
            else:
                diagnostic["body_complete"] = True
        except httpx.TimeoutException:
            diagnostic["read_error"] = "timeout"
        except httpx.DecodingError:
            diagnostic["read_error"] = "decode_error"
        except Exception:
            diagnostic["read_error"] = "read_error"
        finally:
            response.close = original_close
        if close_failed:
            diagnostic["read_error"] = "close_error"
        diagnostic["captured_bytes"] = len(prefix)
        patterns = self._credential_patterns()
        redacted = any(pattern in prefix for pattern in patterns)
        if not diagnostic["body_complete"] and not redacted:
            redacted = any(
                prefix.endswith(pattern[:length])
                for pattern in patterns
                for length in range(1, min(len(pattern), len(prefix) + 1))
            )
        body = b"" if redacted else bytes(prefix)
        diagnostic.update(body_base64=base64.b64encode(body).decode("ascii"),
                          retained_bytes=len(body), body_redacted=redacted)

    def receive(self, payload: dict) -> bytes:
        if not self.enabled:
            raise PermissionError("live provider access is disabled")
        if self.endpoint != self.ENDPOINT:
            raise ValueError("unapproved Nebius endpoint")
        if payload.get("model") != self.model:
            raise ValueError("frozen provider model identity mismatch")
        messages = payload.get("messages")
        if (
            not isinstance(messages, list) or not messages or not isinstance(messages[0], dict)
            or messages[0].get("role") != "system"
            or type(payload.get("n")) is not int or payload["n"] != 1
            or payload.get("stream") is not False
        ):
            raise ValueError("unsupported native request envelope")
        include_context = any(
            isinstance(tool, dict) and isinstance(tool.get("function"), dict)
            and tool["function"].get("name") == "read_context_artifact"
            for tool in payload.get("tools", [])
        ) if isinstance(payload.get("tools"), list) else False
        request_options = {"include_context": True} if include_context else {}
        names = {tool["function"].get("name") for tool in payload.get("tools", [])
                 if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
                 and isinstance(tool["function"].get("name"), str)} \
            if isinstance(payload.get("tools"), list) else set()
        if {"load_skill", "read_skill_resource"} <= names:
            request_options["include_skills"] = True
        # Preserve legacy subclass signatures and their admission checks.
        # Context opt-in still requires the subclass to explicitly support it.
        expected = self.build_request(
            messages[1:], messages[0].get("content"), payload.get("max_tokens"), **request_options,
        )
        if canonical_bytes(payload) != canonical_bytes(expected):
            raise ValueError("unsupported native request envelope")
        payload_digest = digest_json(payload)
        diagnostic = None
        request_started_at = datetime.now(timezone.utc).isoformat()
        try:
            with self.client.stream(
                "POST", self.endpoint + "chat/completions", json=payload,
                headers={"Authorization": "Bearer " + self.key}, follow_redirects=False,
            ) as response:
                if not 200 <= response.status_code < 300:
                    observed_at = datetime.now(timezone.utc).isoformat()
                    diagnostic = {
                        "schema": 1, "kind": "nebius_http_error", "provider": "nebius",
                        "protocol": "chat_completions", "endpoint": self.endpoint,
                        "method": "POST", "path": "chat/completions", "model": self.model,
                        "payload_digest": payload_digest, "request_started_at": request_started_at,
                        "observed_at": observed_at, "status_code": response.status_code,
                        "headers": {}, "headers_limited": False, "body_base64": "",
                        "captured_bytes": 0, "retained_bytes": 0, "body_complete": False,
                        "body_truncated": False, "body_redacted": False, "read_error": None,
                    }
                    diagnostic["headers"], diagnostic["headers_limited"] = self._error_headers(response)
                    self._error_body(response, diagnostic)
                else:
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise ProtocolError("provider response byte bound exceeded")
                        chunks.append(chunk)
        except Exception:
            if diagnostic is None:
                raise
            diagnostic["read_error"] = "close_error"
        if diagnostic is not None:
            # Raise only after context exit; never attach HTTPX request/response
            # objects or an arbitrary transport exception to the public error.
            raise NebiusHTTPError(diagnostic) from None
        return b"".join(chunks)

    def complete(self, payload: dict) -> ModelResponse:
        raw = decode_provider_payload(self.receive(payload), self.max_bytes)
        return parse_nebius_response(raw, self.model)

    def request(self, messages: list[dict], system: str, max_tokens: int = 1024) -> tuple[dict, ModelResponse]:
        payload = self.build_request(messages, system, max_tokens)
        return payload, self.complete(payload)


def context_capability(model) -> str:
    """Fixed adapter continuation contract; response text never grants support."""
    if type(model) is ScriptedModel:
        return "scripted_tool_result_offload_v1"
    if type(model) is NebiusChatCompletions:
        return "nebius_chat_completions_tool_result_offload_v1"
    if type(model) is AnthropicMessages:
        return "anthropic_full_history_v1"
    raise ValueError("unsupported context adapter")


def skills_capability(model) -> str:
    """Explicit immutable-skills support, independent of continuation/offload."""
    if type(model) is ScriptedModel:
        return "scripted_immutable_skills_v1"
    if type(model) is NebiusChatCompletions:
        return "nebius_chat_completions_immutable_skills_v1"
    raise ValueError("unsupported skills adapter")
