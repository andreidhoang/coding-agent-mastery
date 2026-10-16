# Supported repair provider approval boundary

Implemented and inspected **2026-10-10**, Asia/Ho_Chi_Minh. AI-written source; mock transport evidence only. This slice changes `service/repair_provider.py` and `tests/test_repair_provider.py`. It does not change the legacy adapter, harness, billing envelope or master learning evidence.

## Purpose, owners and invariants

The operator owns one public approval tying provider, protocol, exact endpoint/model, token/byte bounds, rate snapshot and source evidence together. The runner consumes its immutable digest before model dispatch. The server owns the separate API key; this module neither discovers credentials nor queries a catalog. The native adapter owns transport and enforces the approved output/request bounds. The harness/runtime retain their existing dispatch, billing and checkpoint authority.

A model name cannot establish a price or token cap: the same spelling can occur at different providers or endpoints. The approval therefore hashes the entire normalized public configuration. Changing any rate, bound, evidence identity, endpoint or model changes its digest. Returned dictionaries and caller inputs cannot mutate that authority. Missing and unknown fields fail; no price, model or evidence defaults are supplied.

**VI:** Approval là “phiếu cấu hình đã khóa”, không phải receipt của lần gọi. Nó chọn chính xác hợp đồng sẽ dùng trước khi gửi; response và billing receipt vẫn phải được lưu và kiểm độc lập sau dispatch. Chuỗi evidence do operator ký nhận không tự biến thành proof đã gọi catalog.

Sources/contracts inspected: [execution specification](../../hackathon/04-execution-specification.md), [provider research](provider-and-research.md), [execution audit §4](execution-contract-audit.md#4-provider-admission-exact-endpoints-and-offline-e2e), [existing adapter](../../service/providers.py), [existing envelope](../../service/billing.py). Global inference dispatch remains `POST https://api.tokenfactory.nebius.com/v1/chat/completions`.

## Frozen schema and API

`ProviderApproval.from_dict` requires precisely these fields:

| Field | Required value/meaning |
|---|---|
| `schema` | Integer `1`, excluding boolean |
| `provider` | `nebius` |
| `protocol` | `chat_completions` |
| `endpoint` | Exact existing adapter base URL `https://api.tokenfactory.nebius.com/v1/` |
| `model` | Exact case-sensitive `nvidia/` ID with a nonempty ASCII alphanumeric/dot/underscore/hyphen suffix |
| `rate_snapshot` | Exact existing `ProviderEnvelope.FIELDS`, validated for this same model |
| `evidence` | Exact `{kind, identity}`; kind `mock` or `operator-verified` |
| `max_response_bytes` | Integer `1..2_000_000`, excluding boolean |

The rate fields are exactly `schema`, `unit`, `rate_id`, `model`, `input_token_bound`, `max_output_tokens`, `input_per_million`, `output_per_million`, `cache_read_per_million`, `cache_write_per_million`, `bound_evidence`, `max_request_bytes`. Rates use integer micro-USD per million tokens; token and request bounds are positive integers. Existing supported output ceiling remains 32,768. Additionally, Nebius approvals require `cache_read_per_million <= input_per_million`: absent cache detail conservatively bills input at the input rate.

Evidence identity must be nonblank with no leading/trailing whitespace or control characters, and carry a source-reference marker (`:`, `/`, `.md` or `.json`). This checks reference shape; it does not resolve links or verify referenced contents. `operator-verified` means an operator assertion referencing catalog/conformance/rate evidence. All account availability, capability, authoritative bound/price and spend facts remain external inputs. Public config must not contain keys or credentials; unknown credential fields are rejected at every schema level.

| API | Result/behavior |
|---|---|
| `ProviderApproval.from_dict(config)` | Validated frozen approval; raw constructor is refused |
| `approval.as_dict()` | New detached public dictionary |
| `approval.digest` | SHA-256 of existing project canonical JSON bytes |
| `approval.model` | Exact model identity |
| `approval.rate_snapshot` | New detached rate dictionary |
| `approval.matches(adapter)` | Boolean; verifies native adapter identity/response cap, any exposed provider/protocol/output/request bounds, built-adapter approval digest, and mock transport isolation where required |
| `approval.build_adapter(api_key, *, enable_network=False, client=None)` | Native Nebius subclass, disabled by default; no HTTP send during construction |

The adapter subclass remains accepted by the existing harness's `isinstance` checks. It rejects excessive output/request bounds and approval drift again at request construction/dispatch. `max_output_tokens` comes from `rate_snapshot`; there is no competing top-level cap. A plain external native adapter does not expose its own output/request caps, so `matches` compares those bounds only when available; the runner must still bind the contract to the approved rate snapshot.

Mock approvals require an explicit exact `httpx.Client` whose default transport and every nonempty mounted transport are `httpx.MockTransport`. This applies even to disabled mock construction, so mock config never silently constructs a live client. Merely supplying a mock default transport with a live HTTPS mount is rejected. Operator-verified approvals permit construction of a default live client, but only the explicit `enable_network=True` flag enables dispatch. There is no production CLI mock toggle or implicit network enablement in this module.

**VI:** Tiny trace: caller tạo config A → `from_dict` giữ canonical bytes A → caller sửa dict A thành B → digest và rates của approval vẫn là A. Với mock, thay client bằng live hoặc thêm live mount làm `matches` trả False, và adapter từ chối trước HTTP. Có `enable_network=True` không đủ để mock approval được gửi ra Internet.

## Distinguishing verification

AI prediction before implementation: malformed or changed public identities should reject before a handler runs; editing input/exported dictionaries should preserve digest; mock approval with default/live/mixed transport should reject; a bounded mock request should send exactly once. Observed in focused tests: all these controls pass. This is mechanics evidence, not learned repair capability, account availability, paid inference or human mastery.

- **62 focused tests passed**, `pytest -q tests/test_repair_provider.py`, Python **3.12.11**, HTTPX **0.28.1**.
- **Ruff clean**, `ruff check service/repair_provider.py tests/test_repair_provider.py`.
- Expanded compatibility observation at this subtask's cutoff: `tests/test_repair_provider.py` plus `tests/test_nebius_provider.py` yielded **124 passed, 5 failed**. All five failures were existing native terminal/replay equality checks with differing `checkpoint_id`, while the runner owner was editing the harness. Reported to that owner; this note does not claim the integrated suite passed or a repair was completed outside assigned files.
- `service/repair_provider.py` SHA-256: `b91fd7a95ef527d7118f3c10522196b286670c2eb035c83e99d3ed5d76b0354d`.
- `tests/test_repair_provider.py` SHA-256: `dd6a38cb350143a1870e2d085dd3563f55f1b85a906af6bd83245ca5fa0dbed9`.

Controls cover unsupported schema/provider/protocol/model/endpoint; boolean/numeric bounds; model/rate mismatch and cache premium; missing/unknown/secret fields; malformed evidence; deep detachment; canonical order invariance; direct-construction bypass; explicit flag/key validation; mock/live/mounted transport denial; case-sensitive identity; adapter/rate/client drift; exact endpoint and single request; operator live construction without catalog/contact. The module does not resolve evidence references, authenticate the catalog, fetch a price, validate real token-bound semantics or authorize spend.

Remaining integration work belongs to the runner owner: freeze this approval digest with the task/run, validate it before dispatch/resume, pass the same rate snapshot to the harness and require explicit CLI enablement plus server-held credential for operator-verified live execution. Mock E2E uses the real native adapter via the trusted injection seam. Stronger operator catalog validation and paid model conformance remain unmeasured external gates.
