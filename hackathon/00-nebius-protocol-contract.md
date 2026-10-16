# Nebius provider implementation contract

Prepared 2026-10-10 for the NVIDIA x Nebius Coding and Agentic Engineering submission. AI-authored design; authenticated catalog, paid inference and live coding capability are pending. This first slice extends the existing durable harness, while the generalized repository runner and grader remain separate work.

**Status navigation, 2026-10-11:** the text below preserves the initial E0 contract and its historical gaps. Later [HTTP diagnostics](06-http-error-evidence-contract.md) and [supported repair/provider approval](05-local-repair-runbook.md) implement bounded extensions, including error evidence and exact provider configuration. Use [current readiness](../research/system-readiness-plan-2026-10-11.md) for delivery status; the initial “currently unavailable” and “future work” wording is not the current coverage register. Live-model and public-access gates remain open.

## Purpose and owners

The provider adapter translates a frozen coding task into Nebius Chat Completions requests and complete responses into validated proposals. It cannot grant repository access, execute tools, accept a patch, or approve a price. The operator owns endpoint/model/rate configuration; the authority store owns dispatch and money reservations; the artifact store owns immutable wire evidence; the harness owns native message continuation; the tool broker owns capability checks and effects; the external verifier owns correctness receipts.

**VI:** Đổi URL trong adapter Anthropic chưa đủ: cấu trúc tool call, tool result và cách tính cached token khác nhau. Adapter mới phải giữ protocol gốc; chỉ proposal đã validate mới đi qua broker, không gọi tool trực tiếp từ HTTP response.

## Required invariants

| ID | Contract | Distinguishing experiment |
|---|---|---|
| NB01 | Explicit exact model and approved HTTPS Nebius endpoint; disabled network by default; no automatic retry or redirects | Disabled adapter sends zero requests; a foreign endpoint is rejected; timeout produces one request only |
| NB02 | Nonstreaming, one choice, bounded complete UTF-8/strict JSON; native assistant/tool messages | Duplicate keys, incomplete JSON, extra choices, wrong role and unknown finish reason reject |
| NB03 | Retain exact complete response body before parsing; billing is independent of semantic acceptance | `length` with valid usage settles charge, persists body and executes zero tools; malformed usage retains liability |
| NB04 | Complete function call ID/name/argument object and exact known tool schema; unique IDs and linked tool results | Invalid/duplicate calls, orphan results and missing results reject before a subsequent request |
| NB05 | Only `tool_calls` with actual complete tools or `stop` without tools can progress | `length`, `content_filter`, missing/wrong finish state never authorize edits |
| NB06 | Native assistant message and optional reasoning/provider fields survive continuation unchanged | Mock first response contains opaque reasoning field; second request carries it and the linked `role: tool` result |
| NB07 | Prompt and completion usage counters are authenticated-response evidence, never model text | Negative, boolean, missing and overflowing counters reject; cached greater than prompt rejects |
| NB08 | Cached prompt tokens are a subset; normalize into disjoint counters for the existing rate envelope | Prompt 100, cached 30 maps to input 70 + cache read 30, never 100 + 30; reasoning subset is not charged twice |
| NB09 | Existing frozen-envelope, request bound, token bound, owner fencing, duplicate-dispatch and checkpoint behavior is preserved | Mock harness records model intent before HTTP; replay reads saved bytes, sends no new HTTP and cannot repeat an unresolved effect |
| NB10 | Provider model identity is checked against the configured supported response identity | Wrong model response retains billing/raw evidence but executes no tools; aliases need an explicit future mapping |

**VI:** Có ba kết luận khác nhau: đã nhận response, đã biết khoản charge, và response có tool proposal hợp lệ. Một response bị cắt do output limit vẫn có thể tốn tiền; parse lỗi không được xóa evidence hoặc giải phóng reservation tùy tiện.

## Wire and billing contract

Request: explicit `model`, `messages`, function `tools`, `n=1`, `stream=false`, bounded output cap and `tool_choice=auto`. Use one documented output-cap field; initial adapter uses `max_tokens`, and the live preflight must verify its enforcement for the selected model, including reasoning. A model whose cap semantics are unsupported cannot be enabled merely because its name appears in documentation.

Response: exactly one choice with index 0 and assistant message. Function arguments arrive as a JSON string and undergo the same strict parser and ToolCall validation as other adapters. Native continuation is `assistant.tool_calls` followed by one `role: tool` message per `tool_call_id`, in order. Do not convert this history into Anthropic content blocks. Keep complete response bytes as the source of billing and protocol evidence.

Normalize `prompt_tokens = P`, cached subset `C`, `completion_tokens = O` to `input_tokens=P-C`, `cache_read_input_tokens=C`, `output_tokens=O`. Optional reasoning count is a subset of completion, not extra output. Require nonnegative integer counts, `C <= P`, and consistent total when present. The documented nullable tool-call/detail fields and nullable counters mean absent evidence; preserve their original null values in raw/native history. Missing cached evidence bills all prompt at the undiscounted input rate. This first Nebius slice rejects approved envelopes with `r_cache > r_input` before dispatch, so that fallback cannot understate a possible cache charge. Integer micro-USD charge is `ceil(((P-C)*r_input + C*r_cache + O*r_output)/1_000_000)`, where each rate is micro-USD per million tokens. Every reservation must cover the enforced input and total output bounds.

**VI:** Nếu P=100, C=30 thì ta đã tính cả 30 cached token trong 100 prompt token. Trừ C trước khi cộng phí cache để tránh double count. Output reasoning cũng nằm trong completion nếu provider định nghĩa như vậy; phải kiểm tra semantics thật trước live run.

## Source and scope

Start from the inspected `service/providers.py`, `service/harness.py`, `service/context.py`, `service/protocol.py` and `service/billing.py`. Primary API/model evidence and documentation conflicts are retained in [provider research](../research/hackathon-2026-10-10/provider-and-research.md). The first implementation allows only the documented global endpoint. Regional endpoints are a future explicitly reviewed extension; Nebius warns that regional URLs may stop working after capacity relocation. No fabricated price/model default is embedded in source.

Acceptance for this slice is deterministic mock HTTP -> native tool call -> guarded workspace read/edit -> next native request -> exact raw evidence and conservative ledger, with existing Anthropic/scripted regressions passing. This is provider protocol evidence. Complete successful entity bodies are retained; HTTP error bodies/headers are currently unavailable after status rejection, and conservative liability remains. Rate approvals are keyed by model in the existing gateway; provider/endpoint binding is enforced in immutable request evidence and replay, with a stronger provider-keyed configuration approval still future work. A real NVIDIA-model call, unseen repository repair, independent grader and public demo remain separate acceptance gates.

**VI:** Mock test chứng minh adapter nói đúng ngôn ngữ của API và không phá invariant runtime. Nó không chứng minh Nemotron sửa được bug, account có model đó, hoặc endpoint áp dụng đúng token cap; các gate đó cần live preflight có budget rõ.
