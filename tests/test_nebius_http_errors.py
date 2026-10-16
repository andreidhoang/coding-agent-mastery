"""Independent synthetic transport/error authority probes; no live calls or keys."""

import base64
import copy
import gzip
import json
import traceback
from datetime import datetime, timezone

import httpx
import pytest

import service.harness as harness_module
from service.artifacts import canonical_bytes, digest_bytes, digest_json
from service.protocol import ProtocolError
from service.providers import AnthropicMessages, NebiusChatCompletions, NebiusHTTPError
from test_nebius_provider import MODEL, call, harness_for, response, setup


SECRET = 'synthetic-secret-"\\-never-real-719ce4'
ERROR_TYPE = "application/vnd.coding-agent.provider-transport-error+json"
TRANSPORT_FIELDS = {
    "schema", "kind", "provider", "protocol", "endpoint", "method", "path", "model",
    "payload_digest", "request_started_at", "observed_at", "status_code", "headers",
    "headers_limited", "body_base64", "captured_bytes", "retained_bytes", "body_complete",
    "body_truncated", "body_redacted", "read_error",
}
ALLOWED_HEADERS = {
    "x-request-id", "request-id", "retry-after", "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests", "x-ratelimit-reset-requests", "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens", "ratelimit-limit",
    "ratelimit-remaining", "ratelimit-reset",
}


class EntityStream(httpx.SyncByteStream):
    """Observe network chunks consumed and inject failures without real transport."""

    def __init__(self, chunks, *, read_failure=None, close_failure=None):
        self.chunks = chunks
        self.read_failure = read_failure
        self.close_failure = close_failure
        self.yielded = 0
        self.eof = False
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk
        if self.read_failure:
            raise self.read_failure
        self.eof = True

    def close(self):
        self.closed = True
        if self.close_failure:
            raise self.close_failure


def adapter(handler, **options):
    return NebiusChatCompletions(
        SECRET, MODEL, enable_network=True,
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True), **options,
    )


def observe(body=b"synthetic failure", *, status=429, headers=None, stream=None, **options):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers=headers,
                              **({"stream": stream} if stream is not None else {"content": body}))

    model = adapter(handler, **options)
    before = datetime.now(timezone.utc)
    payload = model.build_request([], "policy")
    with pytest.raises(NebiusHTTPError) as caught:
        model.receive(payload)
    after = datetime.now(timezone.utc)
    diagnostic = caught.value.as_dict()
    assert len(requests) == 1
    assert set(diagnostic) == TRANSPORT_FIELDS
    assert diagnostic["payload_digest"] == digest_json(payload)
    assert diagnostic["schema"] == 1 and diagnostic["kind"] == "nebius_http_error"
    assert diagnostic["provider"] == "nebius" and diagnostic["protocol"] == "chat_completions"
    assert diagnostic["endpoint"] == NebiusChatCompletions.ENDPOINT
    assert diagnostic["method"] == "POST" and diagnostic["path"] == "chat/completions"
    assert diagnostic["model"] == MODEL and diagnostic["status_code"] == status
    started = datetime.fromisoformat(diagnostic["request_started_at"])
    observed = datetime.fromisoformat(diagnostic["observed_at"])
    assert started.utcoffset() == observed.utcoffset() == timezone.utc.utcoffset(None)
    assert before <= started <= observed <= after
    retained = base64.b64decode(diagnostic["body_base64"], validate=True)
    assert diagnostic["retained_bytes"] == len(retained)
    return caught.value, diagnostic, retained, requests


def stored_error(artifacts, task, state):
    dispatch = state["dispatches"][0]
    ref = dispatch["result_ref"]
    assert ref["content_type"] == ERROR_TYPE
    assert ref["tenant_id"] == "tenant" and ref["task_id"] == task["task_id"]
    encoded = artifacts.get("tenant", task["task_id"], ref["digest"])
    wrapper = json.loads(encoded)
    assert encoded == canonical_bytes(wrapper)
    assert set(wrapper) == {"schema", "kind", "dispatch_id", "request_ref", "request_digest", "transport"}
    assert wrapper["schema"] == 1 and wrapper["kind"] == "provider_transport_error"
    assert wrapper["dispatch_id"] == dispatch["dispatch_id"]
    request = artifacts.get_json("tenant", task["task_id"], wrapper["request_ref"]["digest"])
    assert wrapper["request_digest"] == digest_json(request) == dispatch["input_digest"]
    assert wrapper["transport"]["payload_digest"] == digest_json(request["payload"])
    assert request["provider"] == wrapper["transport"]["provider"] == "nebius"
    assert request["endpoint"] == wrapper["transport"]["endpoint"] == NebiusChatCompletions.ENDPOINT
    assert request["payload"]["model"] == wrapper["transport"]["model"] == MODEL
    return wrapper


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_http_error_evidence_binds_request_preserves_liability_and_never_replays(tmp_path, status):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []
    body = b'{"error":{"message":"synthetic reject"}}'

    def handler(request):
        requests.append(request)
        current = store.snapshot("tenant", task["task_id"])["dispatches"][0]
        assert current["effect_state"] == "in_flight" and current["result_ref"] is None
        return httpx.Response(status, content=body, headers={"X-Request-ID": "request-fixture",
                                                           "Retry-After": "Wed, 21 Oct 2030 07:28:00 GMT"})

    model, harness = adapter(handler), harness_for(store, artifacts)
    with pytest.raises(NebiusHTTPError) as caught:
        harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    dispatch = state["dispatches"][0]
    wrapper = stored_error(artifacts, task, state)
    assert wrapper["transport"] == caught.value.as_dict()
    assert wrapper["transport"]["headers"] == {
        "x-request-id": ["request-fixture"], "retry-after": ["Wed, 21 Oct 2030 07:28:00 GMT"],
    }
    assert base64.b64decode(wrapper["transport"]["body_base64"]) == body
    assert wrapper["transport"]["body_complete"] and wrapper["transport"]["read_error"] is None
    assert dispatch["effect_state"] == "unknown" and dispatch["billing_state"] == "liability_unknown"
    assert dispatch["actual_units"] is None and dispatch["bound_units"] > 0
    assert state["budget"]["spent"] == 0 and state["budget"]["reserved"] == 100
    assert not state["checkpoints"] and workspace.snapshot() == {"a.py": "old"}
    files = {path: path.read_bytes() for path in artifacts.root.rglob("*") if path.is_file()}
    with pytest.raises(RuntimeError, match="unresolved model dispatch"):
        harness.run(owner, task["contract"], workspace, model)
    assert len(requests) == 1
    assert store.snapshot("tenant", task["task_id"])["dispatches"] == state["dispatches"]
    assert {path: path.read_bytes() for path in artifacts.root.rglob("*") if path.is_file()} == files


def test_valid_looking_tool_and_usage_error_has_no_completion_authority(tmp_path, monkeypatch):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    fake = response([call("never", "replace_text", {
        "path": "a.py", "expected_digest": digest_bytes(b"old"), "old": "old", "new": "new",
    })])
    body = canonical_bytes(fake)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, content=body)

    monkeypatch.setattr(harness_module, "parse_nebius_usage", lambda raw: pytest.fail("error usage parsed"))
    monkeypatch.setattr(harness_module, "parse_nebius_response", lambda *args: pytest.fail("error model parsed"))
    model, harness = adapter(handler), harness_for(store, artifacts)
    with pytest.raises(NebiusHTTPError):
        harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    assert len(state["dispatches"]) == len(requests) == 1
    assert state["dispatches"][0]["actual_units"] is None
    assert state["budget"]["spent"] == 0 and not state["checkpoints"]
    assert workspace.snapshot() == {"a.py": "old"}
    wrapper = stored_error(artifacts, task, state)
    assert base64.b64decode(wrapper["transport"]["body_base64"]) == body


@pytest.mark.parametrize("guard", ["content_type", "wrapper_kind"])
def test_late_succeeded_settlement_keeps_independent_diagnostic_replay_guards(tmp_path, monkeypatch, guard):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []
    original_put = artifacts.put

    def put(tenant, task_id, data, content_type="application/octet-stream"):
        if content_type == ERROR_TYPE:
            if guard == "content_type":
                data = canonical_bytes(response([call()]))
            else:
                content_type = "application/json"
        return original_put(tenant, task_id, data, content_type)

    monkeypatch.setattr(artifacts, "put", put)

    def handler(request):
        requests.append(request)
        return httpx.Response(500, content=b"synthetic error")

    model, harness = adapter(handler), harness_for(store, artifacts)
    with pytest.raises(NebiusHTTPError):
        harness.run(owner, task["contract"], workspace, model)
    dispatch = store.snapshot("tenant", task["task_id"])["dispatches"][0]
    store.finish_dispatch("tenant", dispatch["dispatch_id"], "independent-late-receipt", "succeeded", 0,
                          dispatch["result_ref"])
    settled = store.snapshot("tenant", task["task_id"])["dispatches"][0]
    assert settled["result_ref"] == dispatch["result_ref"]
    assert settled["billing_state"] == "settled" and settled["effect_state"] == "succeeded"
    monkeypatch.setattr(harness_module, "parse_nebius_usage", lambda raw: pytest.fail("diagnostic usage parsed"))
    monkeypatch.setattr(harness_module, "parse_nebius_response", lambda *args: pytest.fail("diagnostic parsed"))
    with pytest.raises((RuntimeError, ProtocolError), match="diagnostic|transport.error"):
        harness.run(owner, task["contract"], workspace, model)
    assert len(requests) == 1
    state = store.snapshot("tenant", task["task_id"])
    assert len(state["dispatches"]) == 1 and not state["checkpoints"]
    assert workspace.snapshot() == {"a.py": "old"}


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_enabled_client_sends_once_and_drops_location(status):
    error, diagnostic, _, requests = observe(status=status, headers={
        "Location": "https://evil.invalid/?credential=" + SECRET,
        "Set-Cookie": SECRET, "X-Request-ID": "redirect-fixture",
    })
    assert len(requests) == 1 and diagnostic["headers"] == {"x-request-id": ["redirect-fixture"]}
    assert "evil.invalid" not in json.dumps(diagnostic)
    assert SECRET not in str(error) + repr(error)


@pytest.mark.parametrize("body", [b"", b"\x00\xff\x80\x01", b'{"incomplete":', b"not JSON\xff"])
def test_empty_binary_and_malformed_error_bodies_are_complete_diagnostics(body):
    _, diagnostic, retained, _ = observe(body)
    assert retained == body and diagnostic["captured_bytes"] == len(body)
    assert diagnostic["body_complete"] is True and diagnostic["body_truncated"] is False
    assert diagnostic["body_redacted"] is False and diagnostic["read_error"] is None


@pytest.mark.parametrize("limit", [17, 65536, 100000])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_error_cap_counts_entity_bytes_exact_eof_and_first_overflow(limit, offset):
    cap = min(limit, 65536)
    body = b"a" * (cap + offset)
    stream = EntityStream([body[:7], body[7:], b"unconsumed-overflow"] if offset == 1
                          else [body[:7], body[7:]])
    _, diagnostic, retained, _ = observe(stream=stream, max_response_bytes=limit)
    assert diagnostic["captured_bytes"] == min(len(body), cap)
    assert retained == body[:cap]
    assert diagnostic["body_complete"] is (offset <= 0)
    assert diagnostic["body_truncated"] is (offset > 0)
    assert diagnostic["read_error"] == ("body_limit" if offset > 0 else None)
    assert stream.closed
    if offset > 0:
        assert stream.yielded == 2 and not stream.eof
    else:
        assert stream.eof


@pytest.mark.parametrize("failure,category", [
    (httpx.ReadTimeout("unsafe echo " + SECRET), "timeout"),
    (httpx.ReadError("unsafe echo " + SECRET), "read_error"),
    (httpx.DecodingError("unsafe echo " + SECRET), "decode_error"),
])
def test_post_header_failure_retains_small_prefix_and_safe_category(failure, category):
    prefix = b"available-prefix"
    stream = EntityStream([prefix[:4], prefix[4:]], read_failure=failure)
    error, diagnostic, retained, _ = observe(stream=stream, headers={"Request-ID": "partial-id"})
    assert retained == prefix and diagnostic["captured_bytes"] == len(prefix)
    assert diagnostic["headers"] == {"request-id": ["partial-id"]}
    assert diagnostic["read_error"] == category and diagnostic["body_complete"] is False
    assert diagnostic["body_truncated"] is False
    assert stream.closed
    formatted = "".join(traceback.format_exception(error))
    assert SECRET not in formatted and "unsafe echo" not in formatted
    assert error.__suppress_context__ is True


def test_context_close_failure_keeps_known_eof_and_prefix():
    stream = EntityStream([b"complete-error"], close_failure=RuntimeError("unsafe echo " + SECRET))
    error, diagnostic, retained, _ = observe(stream=stream)
    assert retained == b"complete-error" and diagnostic["body_complete"] is True
    assert diagnostic["read_error"] == "close_error" and not diagnostic["body_truncated"]
    assert SECRET not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("failure_site,category", [
    ("read_timeout", "timeout"), ("read_error", "read_error"),
    ("decode", "decode_error"), ("close", "close_error"),
])
def test_failed_error_capture_is_still_persisted_unknown_once(tmp_path, failure_site, category):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    failures = {"read_timeout": httpx.ReadTimeout("unsafe " + SECRET),
                "read_error": httpx.ReadError("unsafe " + SECRET),
                "decode": httpx.DecodingError("unsafe " + SECRET)}
    stream = EntityStream([b"small-prefix"], read_failure=failures.get(failure_site),
                          close_failure=RuntimeError("unsafe " + SECRET) if failure_site == "close" else None)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500, stream=stream, headers={"x-request-id": "capture-fault"})

    model, harness = adapter(handler), harness_for(store, artifacts)
    with pytest.raises(NebiusHTTPError):
        harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    diagnostic = stored_error(artifacts, task, state)["transport"]
    assert diagnostic["read_error"] == category
    assert diagnostic["body_complete"] is (failure_site == "close")
    assert base64.b64decode(diagnostic["body_base64"]) == b"small-prefix"
    dispatch = state["dispatches"][0]
    assert dispatch["effect_state"] == "unknown" and dispatch["billing_state"] == "liability_unknown"
    assert state["budget"]["reserved"] == 100 and state["budget"]["spent"] == 0
    assert not state["checkpoints"] and workspace.snapshot() == {"a.py": "old"}
    with pytest.raises(RuntimeError, match="unresolved model dispatch"):
        harness.run(owner, task["contract"], workspace, model)
    assert len(requests) == 1


def test_compressed_error_bound_uses_decoded_entity_and_invalid_encoding_is_diagnostic():
    raw = b"z" * 1000
    compressed = gzip.compress(raw)
    stream = EntityStream([compressed[:9], compressed[9:]])
    _, diagnostic, retained, _ = observe(stream=stream, max_response_bytes=32,
                                         headers={"content-encoding": "gzip", "content-length": str(len(compressed))})
    assert retained == raw[:32] and diagnostic["captured_bytes"] == 32
    assert diagnostic["body_truncated"] and diagnostic["read_error"] == "body_limit"
    invalid = EntityStream([b"definitely-not-gzip"])
    _, diagnostic, retained, _ = observe(stream=invalid, headers={"content-encoding": "gzip"})
    assert retained == b"" and diagnostic["read_error"] == "decode_error"
    assert not diagnostic["body_complete"] and not diagnostic["body_truncated"]


@pytest.mark.parametrize("close_fails", [False, True])
def test_raw_eof_does_not_claim_entity_eof_when_decoder_flush_fails(close_fails):
    class FlushFailure:
        def decode(self, data):
            return data

        def flush(self):
            raise httpx.DecodingError("unsafe decoder flush " + SECRET)

    stream = EntityStream([b"available-decoded-prefix"],
                          close_failure=RuntimeError("unsafe close " + SECRET) if close_fails else None)
    requests = []

    def handler(request):
        requests.append(request)
        result = httpx.Response(500, stream=stream)
        # Inject at HTTPX's decoder boundary, after actual raw iterator EOF.
        result._decoder = FlushFailure()
        return result

    model = adapter(handler)
    with pytest.raises(NebiusHTTPError) as caught:
        model.receive(model.build_request([], "policy"))
    diagnostic = caught.value.as_dict()
    assert stream.eof and stream.closed and len(requests) == 1
    assert not diagnostic["body_complete"] and not diagnostic["body_truncated"]
    assert base64.b64decode(diagnostic["body_base64"]) == b"available-decoded-prefix"
    assert diagnostic["read_error"] == ("close_error" if close_fails else "decode_error")
    assert SECRET not in "".join(traceback.format_exception(caught.value))


def test_header_allowlist_duplicate_value_control_and_total_bounds():
    headers = [("X-Request-ID", "first"), ("x-request-id", "second"), ("X-REQUEST-ID", "third"),
               ("Request-ID", "v" * 300), ("Retry-After", "raw-date-value"),
               ("ratelimit-reset", "unsafe\x01value"), ("ratelimit-remaining", "unsafe\tvalue"),
               ("authorization", SECRET), ("proxy-authorization", SECRET), ("cookie", SECRET),
               ("set-cookie", SECRET), ("location", "https://evil.invalid/"), ("server", "fixture")]
    _, diagnostic, _, _ = observe(headers=headers)
    kept = diagnostic["headers"]
    assert kept == {"x-request-id": ["first", "second"], "request-id": ["v" * 256],
                    "retry-after": ["raw-date-value"]}
    assert diagnostic["headers_limited"] is True
    headers = [(name, "a" * 256) for name in sorted(ALLOWED_HEADERS) for _ in range(2)]
    _, diagnostic, _, _ = observe(headers=headers)
    kept = diagnostic["headers"]
    assert set(kept) <= ALLOWED_HEADERS and diagnostic["headers_limited"]
    assert all(len(values) <= 2 and all(len(value.encode()) <= 256 for value in values)
               for values in kept.values())
    # Counting each retained name once is the least restrictive valid interpretation.
    assert sum(len(name.encode()) + sum(len(value.encode()) for value in values)
               for name, values in kept.items()) <= 4096
    _, again, _, _ = observe(headers=headers)
    assert again["headers"] == kept


def test_header_value_truncation_counts_utf8_without_broken_codepoints():
    _, diagnostic, _, _ = observe(headers=[(b"request-id", ("\u00e9" * 129).encode())])
    assert diagnostic["headers"] == {"request-id": ["\u00e9" * 128]}
    assert diagnostic["headers_limited"]


def test_invalid_ascii_header_name_cannot_be_lossily_normalized_into_allowlist():
    _, diagnostic, _, _ = observe(headers=[(b"x-request-\xffid", b"invalid-name"),
                                          (b"retry-after", b"safe-raw-value")])
    assert diagnostic["headers"] == {"retry-after": ["safe-raw-value"]}


@pytest.mark.parametrize("representation", ["raw", "json_escaped", "split_raw", "split_escaped"])
def test_error_secret_echoes_are_removed_before_any_persistence(tmp_path, representation):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    raw_key = SECRET.encode()
    escaped_key = json.dumps(SECRET)[1:-1].encode()
    echoed = escaped_key if "escaped" in representation else raw_key
    body = b"prefix " + echoed + b" suffix"
    chunks = [body] if "split" not in representation else [body[:13], body[13:19], body[19:]]
    stream = EntityStream(chunks)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500, stream=stream, headers={"x-request-id": echoed.decode()})

    with pytest.raises(NebiusHTTPError) as caught:
        harness_for(store, artifacts).run(owner, task["contract"], workspace, adapter(handler))
    state = store.snapshot("tenant", task["task_id"])
    wrapper = stored_error(artifacts, task, state)
    transport = wrapper["transport"]
    retained = base64.b64decode(transport["body_base64"])
    assert raw_key not in retained and escaped_key not in retained
    assert transport["body_redacted"] and transport["headers_limited"]
    assert transport["captured_bytes"] == len(body) and transport["retained_bytes"] == len(retained)
    assert transport["body_complete"] and not transport["body_truncated"]
    for serialized in [canonical_bytes(state), canonical_bytes(wrapper), str(caught.value).encode(),
                       repr(caught.value).encode(), *[p.read_bytes() for p in artifacts.root.rglob("*")
                                                     if p.is_file()]]:
        assert raw_key not in serialized and escaped_key not in serialized
    assert len(requests) == 1


@pytest.mark.parametrize("representation", ["raw", "json_escaped"])
@pytest.mark.parametrize("boundary", ["cap", "failed_read"])
def test_partial_credential_at_capture_boundary_is_removed(representation, boundary):
    key = (json.dumps(SECRET)[1:-1] if representation == "json_escaped" else SECRET).encode()
    partial = key[:17]
    captured = b"error: " + partial
    stream = EntityStream([captured, b"trailing"] if boundary == "cap" else [captured],
                          read_failure=httpx.ReadError("synthetic failure") if boundary == "failed_read" else None)
    _, diagnostic, retained, _ = observe(stream=stream, max_response_bytes=len(captured))
    assert partial not in retained and diagnostic["body_redacted"] is True
    assert diagnostic["captured_bytes"] == len(captured) and not diagnostic["body_complete"]
    assert diagnostic["read_error"] == ("body_limit" if boundary == "cap" else "read_error")


def test_exception_is_detached_and_validated_with_no_request_or_response_objects():
    error, diagnostic, _, _ = observe(headers={"x-request-id": "safe-id"})
    diagnostic["headers"]["x-request-id"][0] = "mutated"
    diagnostic["status_code"] = 200
    assert error.as_dict()["status_code"] == 429
    assert error.as_dict()["headers"] == {"x-request-id": ["safe-id"]}
    original = error.as_dict()
    reconstructed = NebiusHTTPError(original)
    original["headers"].clear()
    assert reconstructed.as_dict() == error.as_dict()
    for field in ("request", "response", "client", "key", "api_key"):
        assert not hasattr(error, field)
    assert len(str(error)) < 100 and "429" in str(error)
    assert "safe-id" not in str(error) + repr(error)
    assert not isinstance(error, httpx.HTTPStatusError)


@pytest.mark.parametrize("mutation", [
    {"unexpected": "field"}, {"status_code": True}, {"status_code": 200},
    {"captured_bytes": True}, {"retained_bytes": -1}, {"body_base64": "not-base64"},
    {"headers": {"authorization": ["forbidden"]}}, {"headers": {"X-Request-ID": ["wrong-case"]}},
    {"read_error": "arbitrary upstream exception"}, {"observed_at": "2001-01-01T00:00:00"},
])
def test_exception_validator_rejects_noncontract_payload(mutation):
    _, diagnostic, _, _ = observe()
    diagnostic.update(copy.deepcopy(mutation))
    with pytest.raises((ValueError, TypeError, ProtocolError)):
        NebiusHTTPError(diagnostic)


@pytest.mark.parametrize("failure_site", ["artifact", "receipt"])
def test_persistence_failure_keeps_exposure_and_prevents_resend(tmp_path, monkeypatch, failure_site):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests, uploads = [], []
    original_put, original_finish = artifacts.put, store.finish_dispatch

    def put(tenant, task_id, data, content_type="application/octet-stream"):
        if content_type == ERROR_TYPE and failure_site == "artifact":
            raise OSError("synthetic artifact write failure")
        ref = original_put(tenant, task_id, data, content_type)
        if content_type == ERROR_TYPE:
            uploads.append(ref)
        return ref

    def finish(tenant, action, receipt, effect, actual=None, result=None):
        if failure_site == "receipt" and result and result["content_type"] == ERROR_TYPE:
            raise OSError("synthetic receipt write failure")
        return original_finish(tenant, action, receipt, effect, actual, result)

    monkeypatch.setattr(artifacts, "put", put)
    monkeypatch.setattr(store, "finish_dispatch", finish)

    def handler(request):
        requests.append(request)
        return httpx.Response(500, content=b"persist-me-before-receipt")

    model, harness = adapter(handler), harness_for(store, artifacts)
    with pytest.raises(OSError, match="synthetic .* write failure"):
        harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    dispatch = state["dispatches"][0]
    assert dispatch["effect_state"] in {"unknown", "in_flight"} and dispatch["result_ref"] is None
    assert dispatch["billing_state"] in {"liability_unknown", "reserved"} and dispatch["actual_units"] is None
    assert state["budget"]["reserved"] == 100 and state["budget"]["spent"] == 0
    assert not state["checkpoints"] and workspace.snapshot() == {"a.py": "old"}
    assert len(uploads) == (1 if failure_site == "receipt" else 0)
    if uploads:
        assert artifacts.get_json("tenant", task["task_id"], uploads[0]["digest"])["kind"] == "provider_transport_error"
    with pytest.raises(RuntimeError, match="unresolved model dispatch"):
        harness.run(owner, task["contract"], workspace, model)
    assert len(requests) == 1


@pytest.mark.parametrize("mismatch", ["model", "payload_digest"])
def test_harness_rejects_adapter_diagnostic_not_bound_to_trusted_request(tmp_path, monkeypatch, mismatch):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500, content=b"wrong-correlation")

    model = adapter(handler)
    original_receive = model.receive

    def receive(payload):
        try:
            return original_receive(payload)
        except NebiusHTTPError as error:
            diagnostic = error.as_dict()
            diagnostic[mismatch] = "untrusted-model" if mismatch == "model" else "0" * 64
            raise NebiusHTTPError(diagnostic) from None

    monkeypatch.setattr(model, "receive", receive)
    harness = harness_for(store, artifacts)
    with pytest.raises(ValueError, match="diagnostic request mismatch"):
        harness.run(owner, task["contract"], workspace, model)
    state = store.snapshot("tenant", task["task_id"])
    dispatch = state["dispatches"][0]
    assert dispatch["effect_state"] == "unknown" and dispatch["result_ref"] is None
    assert dispatch["actual_units"] is None and dispatch["billing_state"] == "liability_unknown"
    assert state["budget"]["spent"] == 0 and not state["checkpoints"]
    assert all(b"provider_transport_error" not in path.read_bytes()
               for path in artifacts.root.rglob("*") if path.is_file())
    with pytest.raises(RuntimeError, match="unresolved model dispatch"):
        harness.run(owner, task["contract"], workspace, model)
    assert len(requests) == 1


@pytest.mark.parametrize("entrypoint", ["complete", "request"])
def test_convenience_methods_propagate_http_error_without_decoding(entrypoint):
    model = adapter(lambda request: httpx.Response(429, content=canonical_bytes(response([call()]))))
    with pytest.raises(NebiusHTTPError):
        if entrypoint == "complete":
            model.complete(model.build_request([], "policy"))
        else:
            model.request([], "policy")


def test_disabled_and_mismatched_request_are_preflight_without_observed_error():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500)

    model = adapter(handler)
    model.enabled = False
    with pytest.raises(PermissionError):
        model.receive(model.build_request([], "policy"))
    model.enabled = True
    with pytest.raises(ValueError, match="model identity"):
        model.receive({"model": "unapproved"})
    assert not requests


@pytest.mark.parametrize("status", [200, 201, 299])
def test_complete_2xx_remains_exact_raw_bytes_and_anthropic_error_stays_httpx(status):
    body = b"exact invalid-success-body\xff"
    model = adapter(lambda request: httpx.Response(status, content=body))
    assert model.receive(model.build_request([], "policy")) == body
    with pytest.raises(ProtocolError):
        model.complete(model.build_request([], "policy"))
    anthropic = AnthropicMessages(SECRET, MODEL, enable_network=True,
                                 client=httpx.Client(transport=httpx.MockTransport(
                                     lambda request: httpx.Response(429, content=b"anthropic-failure"))))
    with pytest.raises(httpx.HTTPStatusError):
        anthropic.request([], "policy")
