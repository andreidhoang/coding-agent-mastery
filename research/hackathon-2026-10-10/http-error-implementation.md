# Nebius HTTP diagnostic implementation evidence

Recorded **2026-10-10**, Asia/Ho_Chi_Minh. AI-authored bounded implementation and local mock verification against the [frozen contract](../../hackathon/06-http-error-evidence-contract.md). No paid request, account discovery, credential inspection, deployment or human-mastery evidence.

## Delivered behavior and ownership

The native adapter emits `NebiusHTTPError` for observed non-2xx statuses, including redirects. Its closed schema is validated and frozen as canonical bytes; `as_dict()` returns a detached copy. Exception text contains only its classification and numeric status. Request-start time is sampled immediately before opening the one stream; response observation time is sampled when headers are available. Successful responses remain exact entity bytes and Anthropic transport behavior remains unchanged.

The adapter bounds decoded error capture to `min(model.max_bytes, 65_536)`, uses one-byte HTTPX iteration to retain available prefixes before a read failure, and stops on the first byte beyond the cap. It retains only exact allowlisted response headers under the specified duplicate/value/total limits. Configured credential echoes in raw and JSON-escaped forms cause the affected body/header value to be omitted before export; incomplete body suffixes matching credential prefixes also cause body omission. Flags distinguish completeness, truncation and secrecy transformations.

The harness checks trusted request identity, writes the sanitized task-scoped `provider_transport_error` wrapper before the Unknown receipt, and preserves `actual_units=None` with liability retained. Neither apparent completion tools nor apparent usage in an error body are parsed. Ordinary Unknown replay refuses dispatch; a separate content-type guard and reserved-wrapper-kind guard reject diagnostics even after an independently trusted late settlement marks the effect succeeded. No error message enters assistant continuation or a new checkpoint.

**VI:** Ví dụ reservation100 gồm bound3 cho dispatch và allowance97 chưa dùng: HTTP429 không làm bound3 biến mất. Diagnostic là evidence điều tra; parser không nhận nó dù body có JSON tool hợp lệ hoặc operator đã settle charge riêng. Gửi lần hai vẫn cần authority khác mà slice này không tạo.

Changed source paths:

- [service/providers.py](../../service/providers.py): typed immutable diagnostic API, validation, bounded streamed collection, supported credential filtering, decoded EOF/close observation.
- [service/harness.py](../../service/harness.py): correlation/wrapper persistence, conservative receipt and two native replay guards.
- [tests/test_nebius_provider.py](../../tests/test_nebius_provider.py): direct redirect expectation now uses the typed domain exception; one-request assertion preserved.
- [tests/test_nebius_http_errors.py](../../tests/test_nebius_http_errors.py): independently authored contract counterexamples, maintained by the test agent.

## Measured verification

Environment: Python **3.12.11**, HTTPX **0.28.1**. Requests use `httpx.MockTransport` or local trusted fixtures; none contact a live provider.

Final selected regression command:

```text
uv run pytest -q tests/test_nebius_http_errors.py tests/test_nebius_provider.py tests/test_live_harness.py tests/test_repair_provider.py tests/test_repair.py tests/test_repair_boundaries.py tests/test_repair_verification.py tests/test_repair_reporting.py
```

Measured **340 passed, 7 skipped**, **7.75s**, including all **70** finalized independent HTTP diagnostic cases. The seven skips require an explicit already-present immutable sandbox image: one repair integration case and six verification integration cases. Existing FastAPI/Starlette test-client deprecation warning remains; it is unrelated to the HTTP evidence behavior.

```text
uv run ruff check service/providers.py service/harness.py tests/test_nebius_provider.py tests/test_nebius_http_errors.py
```

Measured **all checks passed**. The native/Anthropic/repair selection alone passed **270 tests / 7 skips** before the final focused additions; the combined final selection supersedes that intermediate result.

Counterexamples cover HTTP400/401/403/404/429/500/503; valid-looking error tool/usage envelopes; unchanged workspace and no checkpoint; repeat refusal without another HTTP call; late succeeded diagnostic receipts rejected by either replay guard; redirects with redirect-enabled clients; empty/binary/malformed bodies; cap-minus-one/exact-cap/cap-plus-one and multiple chunks; partial read timeout/error/decode failure; EOF followed by close failure; gzip expansion and invalid encoding; bounded duplicate/control/forbidden/UTF-8 header values; raw/escaped/split/capture-boundary credential echoes; immutable payload validation; artifact/receipt failures; request/config preflight and unchanged success/Anthropic paths.

## Failure evidence and repairs

- An initial implementation failed collection because `raise from None` lacks an exception expression. It was replaced with explicit storage-exception propagation; lint and final regression pass.
- The first independent diagnostic run measured **59 passed / 1 failed**: decoded bytes reached EOF, but HTTPX `iter_raw()` called `close()` before `iter_bytes()` could signal decoded EOF. A failing stream close was misclassified as a read failure and lost completeness evidence. A temporary per-response close observer now preserves the close failure without interrupting decoder completion; `body_complete` is true only if decoded iteration actually finishes, independently of `read_error="close_error"`. The observer is restored before context exit, and no upstream exception string is exported.
- Independent review found that lossy ASCII header-name decoding could transform a forbidden raw name into `x-request-id`. Strict ASCII decoding now rejects that name; the independent test suite includes the counterexample.

**VI:** HTTPX có hai lớp EOF: raw stream hết trước, decoder còn phải flush sau. Observer chỉ trì hoãn việc báo close failure để decoder có thể kết thúc; nó không tự khẳng định body đủ. Header name cũng không được “sửa gần đúng” thành tên allowlist, vì normalize sai sẽ mở thêm quyền thu thập.

## Limits and unverified claims

This is application-level bounded capture, not a hostile-server decompression-bomb defense. HTTPX/decompressor internal allocations remain outside the retained-buffer guarantee. Credential filtering covers only configured material and the explicitly supported raw/JSON-escaped representations, not unrelated secrets or arbitrary encodings. One-byte decoded iteration trades modest loop overhead for precise available-prefix retention under HTTPX buffering; no throughput claim is measured.

Status or Retry-After does not settle billing, authorize tools, sleep/retry, replace an action or choose a fallback provider. Artifact failure attempts existing Unknown receipt without a result reference; receipt failure after upload may leave an orphan artifact and in-flight uncertainty. Both prevent another dispatch in the mock counterexamples. No DB schema change, historical-response rewrite, active-case recovery claim, production-readiness claim, live NVIDIA/Nebius quality result or mastery update is supplied.

Source SHA-256 identities, after the independent test file was finalized:

| Path | SHA-256 |
|---|---|
| `service/providers.py` | `fa370e8688d366969ccb67984b4a28154af8487bb16243e892a8f7a8917e56bf` |
| `service/harness.py` | `ff3b3b6fc9270760fcbd8766aa70ce38cf4374e159977177d0795d8f35e48bd7` |
| `tests/test_nebius_provider.py` | `4886050df6763c5437e2cd59eec1247b5dfd23e2f4022367039d78b7d7855631` |
| `tests/test_nebius_http_errors.py` | `05bfef22804ae3ca40b7b3c5b4f6eb0ef2dc6d11bbdd182a4f11eec2b6738911` |
| `hackathon/06-http-error-evidence-contract.md` | `dd8b4f2389503f273c765d8fe4c48685637d7e77819cf7b7b024597fb3cf70d7` |

Historical JSON verification files and successful-body artifacts retain their previous meaning and hashes.

**Delivery annotation:** the contract SHA above identifies the design-freeze revision before parent delivery annotations and refreshed source anchors. Normative API/schema/limits are unchanged; current integrated source/package results live in [HTTP verification](http-error-verification.json).
