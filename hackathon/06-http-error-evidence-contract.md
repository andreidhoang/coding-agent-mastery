# Nebius HTTP error evidence contract

**Design freeze and subsequent bounded delivery, 2026-10-10.** This closes the HTTP-diagnostic gap identified in [the execution audit](../research/hackathon-2026-10-10/execution-contract-audit.md). Scope is the native Nebius adapter and its harness branch. Preserve Anthropic behavior, successful-response byte artifacts, supported repair approvals and existing accounting/recovery contracts. The contract was specified before implementation; [delivery verification](../research/hackathon-2026-10-10/http-error-verification.json) and [independent review](../research/hackathon-2026-10-10/http-error-independent-review.md) own subsequent measured results. No paid request or account/credential discovery occurred.

## Purpose and authority

A non-2xx response is evidence that an HTTP response was observed. It does not establish a valid model completion, a tool proposal, zero charge or permission to retry. Retain enough bounded diagnostics to investigate the response without losing uncertain exposure or admitting response content as authority.

Pre-implementation rationale: the native adapter called `raise_for_status()` before reading error bodies; the harness recorded Unknown without an artifact, while succeeded-result replay decoded saved bytes as a completion. The delivered [native receive](../service/providers.py#L518), [typed error](../service/providers.py#L352), [diagnostic receipt path](../service/harness.py#L147) and [replay guards](../service/harness.py#L147) now keep error evidence distinct from successful response bytes and ineligible for model parsing, including after later billing/effect reconciliation.

**VI:** HTTP 429 có thể giải thích vì sao request không trả completion; nó chưa chứng minh charge bằng 0. Lưu error body giúp điều tra, nhưng nếu gắn nó nhầm vào đường success rồi replay, một JSON giống tool call có thể đi vào parser sai quyền.

| Owner | Responsibility and invariant |
|---|---|
| Nebius adapter | One HTTP send; collect bounded error status/body/allowlisted response headers; sanitize exported evidence; never parse error tools or settle billing. |
| Harness | Bind diagnostics to the already persisted exact request and dispatch; store artifact before receipt; stop the turn without adding assistant/tool messages. |
| RuntimeStore | Existing intent, Unknown effect, immutable result reference and unsettled reservation; no schema change or new success state. |
| Operator/reconciler | May later supply independently trusted billing/effect evidence under existing rules; error status alone does not authorize reconciliation or another call. |
| Report/API | Inspect the sanitized diagnostic artifact as evidence; no automatic retry countdown, success inference or secret-bearing exception dump. |

## Public Python API and immutable record

Keep `NebiusChatCompletions.receive(payload) -> bytes` for complete 2xx bodies. Add **`NebiusHTTPError(RuntimeError)`** for observed non-2xx responses, including 3xx. The exception exposes `as_dict() -> dict`, returning a detached JSON-safe copy of a validated immutable diagnostic payload. Its `str`/`repr` is a fixed short classification with numeric status only. It exposes no HTTPX request/response/client, API key, headers from the outgoing request, body in the exception message or arbitrary upstream exception string. Raising suppresses unsafe exception chaining in ordinary CLI tracebacks. `complete()` and `request()` propagate it; they never decode its body.

This intentionally changes direct Nebius non-2xx callers from `httpx.HTTPStatusError` to the typed domain error. Update the existing redirect test accordingly; preserve its one-request/no-follow assertion. Anthropic methods and their exception behavior are outside this change. Disabled/configuration/request-validation failures remain their existing preflight errors with zero sends. Exceptions before response headers and incomplete/oversized 2xx behavior remain existing conservative paths in this slice.

**VI:** Typed exception mang evidence đã lọc, không mang cả object request chứa Authorization. API success vẫn trả bytes như trước; chỉ nhánh HTTP error có contract mới nên phạm vi regression rõ ràng.

Adapter payload fields are exact; reject unknown fields in its validator:

```python
{
    "schema": 1,
    "kind": "nebius_http_error",
    "provider": "nebius",
    "protocol": "chat_completions",
    "endpoint": "https://api.tokenfactory.nebius.com/v1/",
    "method": "POST",
    "path": "chat/completions",
    "model": str,
    "payload_digest": str,             # digest_json(payload), no headers/key
    "request_started_at": str,         # UTC ISO-8601 immediately before client.stream
    "observed_at": str,                # UTC ISO-8601, response headers observed
    "status_code": int,                # observed non-2xx; bool forbidden
    "headers": dict[str, list[str]],    # lower-case exact allowlist below
    "headers_limited": bool,
    "body_base64": str,                # bounded retained diagnostic bytes
    "captured_bytes": int,             # prefix bytes before sanitization
    "retained_bytes": int,             # decoded body_base64 length
    "body_complete": bool,             # EOF reached normally
    "body_truncated": bool,            # capture cap exceeded
    "body_redacted": bool,             # retained body differs for secrecy
    "read_error": str | None,          # fixed category, never str(exception)
}
```

`body_complete` describes transport capture, not protocol validity. `body_redacted` independently describes whether retained bytes are transformed. EOF with an empty body is complete. A redacted complete body is not exact raw evidence. Invalid UTF-8/non-JSON bodies are valid diagnostics represented by base64; never permissively decode them as model messages. `request_started_at` is sampled after local validation and immediately before opening the one HTTP stream; the harness durable intent already exists. It describes the local send attempt, not proof the provider accepted it. `observed_at` is sampled when response headers become available, not provider completion time or a deadline authority. Both are timezone-aware UTC and remain distinct from DB dispatch/receipt timestamps; no caller timestamp can backdate authority.

The harness wraps this adapter payload in an exact record:

```python
{
    "schema": 1,
    "kind": "provider_transport_error",
    "dispatch_id": str,
    "request_ref": dict,               # existing task-scoped immutable request
    "request_digest": str,             # digest_json(full native request record)
    "transport": dict,                 # the adapter payload above
}
```

Persist canonical bytes with content type **`application/vnd.coding-agent.provider-transport-error+json`**, using ordinary tenant/task artifact scoping. The wrapper has no top-level `choices`, `usage` or assistant message. Before storing, harness checks adapter provider/endpoint/model/payload digest against the current trusted request, not values claimed by response text. The adapter owns collection; harness adds execution identity it already owns. Never add credentials to the request record to make this correlation.

## Capture limits and credential policy

Freeze error-body cap to **`min(model.max_bytes, 65_536)` decoded entity bytes**. Stream incrementally, retain at most that prefix, and stop at the first byte beyond the cap. Do not buffer the complete response through `response.content`/`read()`. On cap exhaustion set `body_truncated=true`, `body_complete=false`, `read_error="body_limit"`; `captured_bytes` reports the retained prefix length, not an invented full length. EOF exactly at the cap is complete if actually observed. A post-header read/decode failure produces `body_complete=false` and a fixed category `timeout`, `read_error`, or `decode_error`; retain available bounded prefix. A context-manager close failure after a known non-2xx status also produces the typed diagnostic error with `read_error="close_error"`; preserve whether body EOF was already reached. Collect evidence outside the context manager's lifetime so `__exit__` cannot replace it with an unclassified error. No extra HTTP request follows. For Content-Encoding, count HTTPX `iter_bytes` decoded entity bytes, not compressed Content-Length; a small compressed body that expands past the cap is truncated. Invalid encoding after a known status is `decode_error` with its available prefix.

Capture only these case-insensitive header names, normalized to lower case: `x-request-id`, `request-id`, `retry-after`, `x-ratelimit-limit-requests`, `x-ratelimit-remaining-requests`, `x-ratelimit-reset-requests`, `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-tokens`, `x-ratelimit-reset-tokens`, `ratelimit-limit`, `ratelimit-remaining`, `ratelimit-reset`. This is our diagnostic compatibility allowlist, not a claim that Nebius emits every name. Keep at most two values/name, 256 UTF-8 bytes/value, and 4,096 bytes total including retained names/values. Deterministic omission/truncation sets `headers_limited=true`; drop values with control characters. Preserve raw permitted Retry-After text without converting it into retry authority.

Never collect request headers, `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `location`, arbitrary response headers, URL query strings or raw exception messages. Provider key echo is possible even in a permitted header/body. Before export, redact exact occurrences of the configured key and its JSON-string-escaped representation in every retained string/byte field that came from HTTP. Keep model/config identities from trusted configuration, not response echoes. A straightforward safe policy is to omit the entire retained header value/body when such an echo is detected; then set the appropriate limited/redacted flag. For a truncated/failed body prefix, also remove any suffix matching the start of the key or escaped representation so a credential split at the capture boundary is not retained. Short keys that match common text may over-redact; secrecy takes precedence over diagnostic completeness.

**VI:** Header allowlist vẫn chưa đủ vì server có thể echo key vào `x-request-id` hoặc body. Ta giữ bytes chính xác khi có thể; nếu phải bỏ phần chứa key thì ghi redacted rõ ràng, không giả vờ còn raw response nguyên vẹn. Bộ lọc không phải DLP tổng quát cho mọi encoding hoặc secret không được cấu hình.

The supported redaction guarantee covers outgoing credential material the adapter possesses and explicitly described representations. Do not claim detection of unrelated secrets or arbitrary transformations. No raw unredacted error-body artifact is written first. Raw-key hashes, error excerpts and unfiltered headers must not be added to logs as a workaround. Large HTTPX/decompressor internal allocations are outside this application-level capture guarantee; the bounded collector must use fixed-size iteration and never accumulate more than its specified retained buffer. This slice does not claim a hostile-server decompression-bomb defense.

## State, persistence and replay rules

Catch `NebiusHTTPError` **before** the generic exception path and only for the native Nebius adapter. Persist the validated/sanitized wrapper, then call existing `finish_dispatch(tenant, action_id, "unknown-" + action_id, "unknown", None, diagnostic_ref)`. Re-raise the typed error. `actual_units=None` preserves `liability_unknown`; the full dispatch bound remains reserved. Never parse an error body's apparent `usage`, even if it resembles a successful response. Status 400/401/403/404/429/500/503 and redirects have the same conservative accounting policy in v1.

If artifact persistence fails, record Unknown without a result reference through the existing path where possible; surface storage failure and never send another request. If DB receipt persistence fails after upload, the artifact can remain orphaned while dispatch is in-flight/Unknown; replay refuses it. Do not overwrite an already bound result with different error bytes on a retry. A matching persisted diagnostic receipt is reused rather than recreated with a new observation timestamp.

**VI:** Ví dụ claim40, request bound12: trước lỗi còn allowance28 + liability12. Nhận429 rồi lưu diagnostics vẫn là exposure12, không thành0. Retire workspace có thể giải phóng28 chưa dùng; phần12 chỉ được settle từ bằng chứng billing độc lập.

Two independent replay guards are required:

1. Existing duplicate gate refuses any non-`succeeded` model dispatch, so normal error replay sends zero HTTP and performs zero tools.
2. In the native succeeded-result path, reject the diagnostic content type or the reserved `kind="provider_transport_error"` wrapper **before usage/model parsing**. This protects a diagnostic artifact that remains immutable when a trusted late reconciler changes effect/billing knowledge. A known/settled effect is not a successful completion body. Never unwrap `transport.body_base64` into the model parser.

No error is added to assistant native continuation or checkpoint evidence as a model response. A prior checkpoint's advanced/Unknown dispatch frontier prevents clean resume. Settling billing alone does not remove that effect uncertainty. A separately authorized reconciler may resolve facts, but this change supplies no automated retry, retry-after sleep, replacement permission, inferred zero charge or fallback provider.

## Distinguishing tests and exit

Use `httpx.MockTransport` and existing native harness fixtures only; no account/key discovery or live access. A passing count without these counterexamples is insufficient.

| Case | Required observation |
|---|---|
| 429 and 500 complete small bodies | Typed error, saved status/header/body metadata and request binding; one HTTP send; Unknown/liability retained; unchanged workspace. |
| Error body is a valid-looking tool completion with valid usage | Zero tool dispatch, zero settlement, no assistant/checkpoint continuation; diagnostic wrapper retained. |
| Repeat same harness invocation | Zero additional HTTP, no new diagnostic timestamp/artifact/charge; existing Unknown refusal. |
| Late trusted settlement/reconciliation leaves diagnostic result bound | Native replay rejects content type/wrapper before parser even if effect becomes succeeded; no tool or second HTTP. |
| 301/302/307/308 with redirect-enabled injected client | Exactly one request; no follow; no Location or credential-forwarding evidence retained. |
| Empty, binary, malformed JSON, invalid UTF-8 error bodies | Valid bounded diagnostics; never model parsing; body completeness is accurate. |
| Cap minus one, exact cap EOF, cap plus one; multiple chunks | Correct captured/retained counts and complete/truncated flags; bounded buffer and no implicit retry. |
| Read timeout/error after headers and partial body; context close fails after EOF | Status/allowed headers/prefix and observed timestamps retained with fixed read_error; close failure retains known EOF state; no arbitrary exception message; Unknown. |
| Compressed error expands beyond cap; malformed Content-Encoding | Decoded bound enforced; accurate truncated/decode_error state; never trust compressed Content-Length as retained size. |
| Duplicate/oversized/control-character/forbidden headers | Only exact allowed bounded values survive; limited flag accurate; no cookies, Location or request Authorization. |
| Key in body/header, escaped key, split chunks, capture-boundary prefix | No raw or supported escaped key material in exception text, artifact, events/snapshot or serialized report; flags disclose redaction. |
| Artifact write fails; receipt write fails after artifact | Liability remains; replay sends zero requests; no fabricated complete response or successful task. |
| Disabled adapter or mismatched approval/request | Zero HTTP and no new diagnostic pretending a response was observed. |
| Complete 2xx malformed protocol/usage, valid tool loop, timeout before headers | Existing raw-success persistence, billing/semantic separation and conservative timeout behavior preserved. |
| Existing Anthropic tests and supported repair mock integration | No Anthropic behavior change; native approval/bounds/continuation/clean resume remain valid. |

The new exception class and error artifact schema are the only API additions. No store schema migration, broader provider refactor, automatic retries, successful-response wrapper conversion or new evaluator is needed. Source delivery should include focused mock tests, relevant native/Anthropic/repair regressions, lint and a dated evidence record with current source identities. Historical successful-body evidence retains its original hashes and meaning.

**VI:** Phép thử quan trọng nhất là error body cố tình giống completion hợp lệ, rồi thử replay cả sau settlement. Nếu vẫn không có tool và không gửi request lần hai, ta đã kiểm đúng ranh giới authority thay vì chỉ kiểm “lưu được file JSON”.

## Measured delivery

The integrated current source passed662 default tests and156 subtests, with24 explicit backend skips. A separate opted-in native/repair integration selection passed347 tests with no skips, including actual local Docker controls and native-mock full repair. Independent HTTP-focused review passed70 tests. These counts overlap and must not be summed. The curated wheel was imported from a disposable extracted directory, preserving42 authored fixture tasks/82 locked assets plus the supported repair task/recipe. [Verification](../research/hackathon-2026-10-10/http-error-verification.json) binds source, environment, JUnit, package and source-export identities.

Independent testing/review repaired decoded-EOF/close-failure classification and malformed header-name normalization. Successful body handling and Anthropic behavior remain covered. Huy explicitly keeps paid execution disabled; actual NVIDIA/Nebius sponsor use and live coding quality remain pending.
