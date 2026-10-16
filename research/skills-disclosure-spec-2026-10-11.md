# Accepted catalog and loaded-skill disclosure

Date: **2026-10-11**, Asia/Ho_Chi_Minh. Status: **FROZEN BEFORE IMPLEMENTATION — architecture, implementation-seam and independent testability reviews complete**. This specializes dependency step4 of [the frozen parent design](immutable-skills-spec-2026-10-10.md), after [capture](immutable-skills-capture-spec-2026-10-11.md) and [broker step3](skills-broker-spec-2026-10-11.md). Preserve all three contracts. Scope is one immutable fixture, scripted and actual local mock Nebius HTTP, accepted request disclosure and resource authority. Paid execution remains disabled. No installed-skill discovery, account access, credential redemption, script execution, release promotion or human mastery claim.

## Purpose and observable boundary

A load receipt proves that the broker returned captured instructions. It does not prove that any model request contained them. Step4 binds a catalog, receipt-derived membership, exact tool history, rendered system/tools and outgoing provider request to one atomically accepted model intent. Resource authority belongs to that accepted request, even if a later tool in the same response changes loaded state. This enables an auditable model/tool feedback loop; it does not establish that a model obeys or benefits from the instructions.

For package P, ordinary successful primary receipt L and accepted request Q:

- `loaded(P)` requires the unique validated primary L in this owner attempt.
- `disclosed(P,Q)` requires Q's accepted SkillsState to name L and Q's source/projected messages to contain L's exact call and canonical result.
- `read_allowed(P,response(Q))` requires disclosed(P,Q), the latest successful accepted Q for a new call, current owner/capabilities, exact resource membership and valid captured bytes.

**VI:** Receipt là bằng chứng tool đã trả sách; accepted request là bằng chứng trang sách thực sự nằm trong gói gửi cho model. Nếu response Q0 yêu cầu load rồi đọc resource, load có thể commit nhưng quyền đọc vẫn xét Q0 vốn chưa chứa sách. Chỉ Q1 mới làm thay đổi disclosure.

## Inspected seams and ownership

Baseline inspection: `context/current-state.md`, `study/packets/H0-reference-runtime.md`, parent and broker contracts; `service/context.py`, `service/harness.py`, `service/storage.py`, `service/recovery.py`, `service/providers.py`, `service/skill_runtime.py`, `service/skills.py`. Freeze their hashes before code. Existing v1 planner/manifest/request validators are closed; native receive reconstructs schemas; Harness always writes legacy/context checkpoints; broker source validation currently permits only scripted context-v1. These are explicit version seams, not existing disclosure support.

| Owner | Responsibility |
|---|---|
| Trusted launcher | Explicit capture/config and context configuration; one fixed selection for the run |
| Artifact storage/capture | Scoped bounded immutable catalog, package, body and resource bytes |
| Broker/ordinary receipt | Tool provenance, deterministic result and primary-load commit point |
| Disclosure validator | Closed state, direct original receipt proof, exact source history and deterministic prompt/request reconstruction |
| RuntimeStore | Durable record reads; owner/contract/capabilities/frontier/CAS; atomic acceptance plus model intent; receipt immutability |
| Adapter | Exact capability and request schema, actual native send/reconstruction; no authority inferred from prose |
| Harness | Construct next request from raw history and durable evidence, preserve opaque fields, use saved historical state for exact retries |

**VI:** Artifact validator chứng minh bytes đúng trước transaction; store chứng minh evidence và quyền chưa đổi lúc commit. Không giữ database lock trong lúc đọc file. Hash state do caller nộp chỉ là lời khai, chưa phải authority.

## Opt-in, compatibility and public seams

Add keyword-only `skills_capture=None, skills_config=None` to Harness construction. Both absent preserves current behavior and bytes. Exactly one supplied rejects. Both present require explicit valid `context_config`, both `load_skill` and `read_skill_resource` in the frozen contract, configured artifact storage and a supported exact adapter type. Deep-copy the selection and validate its captured artifacts. Never import filesystem paths during a run. Reject Anthropic skills even with full-history context before intent/send; existing disabled Anthropic remains unchanged.

ToolBroker retains step3 by default. Add explicit `skills_mode="broker_skill_loads_v1"`; the new Harness passes `"accepted_skills_v1"`. Reject unknown modes, or accepted mode without capture/config. Mode is a local validation policy, not new persisted authority. Accepted mode admits only context-schema2 source records. Broker mode continues its context-v1 scripted contract and always denies resource disclosure. `derive_loaded_skills` keeps its old exact `kind:"broker_skill_loads_v1"` output and rejects v2 records rather than relabeling them. A new public `derive_skills_state(store, artifacts, owner, capture, config)` returns the parent SkillsState for an accepted-mode attempt; it is a detached description and grants no execution authority. No conversion helper or arbitrary caller seed.

Reject entry into accepted mode if this attempt already contains legacy/context-v1 model history or broker-v1 skill records. Reject skills-disabled continuation of this attempt through the new supported Harness when v2 acceptance already exists. Same-attempt catalog/config and adapter identity must remain fixed across v2 requests. This does not claim old binaries or generic ordinary-dispatch callers enforce task-wide mandatory skills policy. Fresh-owner/imported state is unsupported here.

Keep `RuntimeStore.begin_projected_dispatch(...)` and its public arguments: explicitly dispatch on manifest version. Keep `begin_skill_dispatch(...)` public arguments and closed `skill_call`; inspect the authoritative source version to apply the appropriate profile. Any new evidence fingerprint supplied to private `_begin_dispatch` is computed inside the public store method, never trusted as caller authority. Reuse `read_skill_records(owner)` for bounded evidence and accepted-mode broker pinning. A new helper module `service/skill_disclosure.py` may own rendering/state/provenance functions; helper names beyond the public seams are implementation choices.

**VI:** Hai profile cùng dùng ordinary receipt nhưng bằng chứng khác nhau. Source context-v1 chưa chứng minh catalog đã gửi nên không được đổi nhãn thành v2. Việc tách mode rõ ràng giữ được experiment step3 và tránh migration ngầm.

## Closed objects and exact bytes

`D(x)` means existing canonical JSON SHA-256. All digests lowercase64-hex, all integer checks reject booleans, all artifact references retain the closed existing five fields and tenant/task scope. The capture/config/package profile and limits remain unchanged.

SkillsState exact keys:

```text
{schema:1,catalog_ref,catalog_digest,config_ref,config_digest,loaded,source_checkpoint:null}
loaded = [] or [{package_digest,load_dispatch_id,result_ref}]
```

No `kind` key, mutable active flag or permissions. Serialize canonical JSON, require state reference digest = state digest, cap state artifact at65,536 bytes before read/parse; validate referenced config/catalog/package with existing profile caps. In this step `source_checkpoint`, context manifest `source_checkpoint` and `restored_from_projection_id` must all be null.

Explicit versions exactly follow the parent:

| Object | New supported shape |
|---|---|
| Context manifest | `context_schema:2`; exact v1 keys plus `skills_state_ref`, `skills_state_digest`, `prompt_digest` |
| Binding | Exact v1 keys plus `skills_state_digest` |
| Adapter | Exact v1 keys plus `skills_capability`; `adapter_version:"context_skills_v1"` |
| Projection | `schema:2`; exact v1 keys plus `skills_state_digest` |
| Acceptance | Existing four keys with `context_schema:2`; manifest digest is projection ID as before |
| Context config | Unchanged closed schema1 |
| Persistent store/writer/dispatch parameters | Unchanged schema2/writer protocol/six fields |

Manifest/binding/projection/state must agree on the same state digest. Reject partial/unknown/boolean versions, extra keys, wrong content type, dangling/malformed/oversized or corrupt references. V1 remains closed and byte-identical; explicit version branches must not coerce mixed shapes. `validate_context_manifest` may return validated state/catalog alongside its existing source/projection/request for v2, but performs artifact/request validation only, never an unbounded store walk.

Freeze `skills_prompt_v1` system text as the existing prefix followed by this exact suffix (LF newlines, no trailing newline after catalog):

```python
system = "Follow only the frozen task constraints: " + str(contract["requirements"])
system += "\n\nImmutable skill catalog (untrusted task aids; subordinate to frozen task constraints and capabilities):\n"
system += canonical_bytes(catalog).decode("utf-8")
```

The catalog is exactly the validated stored catalog object; no body, resources, host paths or synthetic loaded instructions are appended. Actual advertised provider tool schemas include both skills tools and include context retrieval only for offload strategy. `system_digest=D(system)`, `tools_digest=D(actual_provider_tools)`, and `prompt_digest=D({renderer:"skills_prompt_v1",system,tools:actual_provider_tools,messages:projected_messages})`. Body and resource bytes occur only in ordinary tool results already in raw history. Loading changes prompt/request identity while catalog/system/capabilities can remain fixed.

Scripted v2 request is the closed concrete record `{schema:1,provider:"scripted",protocol:"anthropic",model:contract.model,system,tools,messages,projection,projection_digest,prompt_digest}`. Here messages equal projected messages, projection is the entire schema2 projection and projection_digest is its canonical digest. This is inspectable scripted evidence with explicit rendered prompt, not an HTTP-send claim. The scripted response model remains `scripted-fixture-v1`. Native request record retains `{provider:"nebius",protocol:"chat_completions",endpoint,payload}` with unchanged payload envelope fields and the v2 rendered system, tools and messages. Request digest includes the entire respective record. Manifest prompt digest is reconstructed from actual request content, not trusted independently.

**VI:** Q0 có catalog nhưng chưa có body; Q1 chứa chính wrapper load trong tool history. Không cần đổi system sau load. Nếu test chỉ xem system hash thì sẽ bỏ sót body bị rơi khỏi payload. Scripted record ghi đủ prompt để so sánh; bằng chứng gửi thật dùng mock HTTP native.

## Providers, planning and admission

Add `skills_capability(model)` with exact adapter-type mapping `ScriptedModel → scripted_immutable_skills_v1`, `NebiusChatCompletions → nebius_chat_completions_immutable_skills_v1`; unsupported types/subclasses/Anthropic reject. This is independent of `context_capability`. Retain exact current offload capability checks and frozen `read_context_artifact` capability for offload. Full-history skills still require skills capability.

Nebius `build_request(..., include_context=False, include_skills=False)` opts into existing strict skills schemas. Receive-side reconstruction recognizes the full skills pair, passes the explicit option and compares the entire canonical expected envelope. Missing one skill, duplicates, extra/changed schemas, model/endpoint/output drift and unsupported partial combinations reject before HTTP. Never waive tools equality. Preserve legacy subclass signatures when options are absent; an unsupported opted-in subclass cannot claim capability. Anthropic default tools/request unchanged.

`plan_context` selects a closed schema2 path from the explicit v2 binding. Both full-history and tool-result-offload strategies remain available. V2 protects results of `load_skill`, `read_skill_resource`, and `read_context_artifact`, regardless of success/error or batch age; validator independently enforces the same eligibility. Other results retain existing deterministic offload rules. A body that does not fit rejects; no trimming, summaries, offloading protected results or removing loaded membership. Raw history, provider opaque fields, call IDs, tool-result error flags and evidence pairs remain exact.

Projection cap remains context config `max_bytes`. Additionally bound the full scripted v2 request by that same `max_bytes` (its explicit wrapper/duplicate projection are counted), and the native payload by frozen ProviderEnvelope `max_request_bytes` with existing output allowance/reservation/token-bound checks. Catalog/system/tools are included. The output token allowance is reserved through existing envelope accounting, not estimated by pretending byte counts are exact tokens. Native receipts may settle positive charge; scripted and skill-tool receipts remain zero. No transport credential enters artifacts. Artifact/serialization overflow before new acceptance leaves any already committed load intact and makes no send.

**VI:** Context projection nhỏ hơn giới hạn chưa đủ nếu system và tool schemas làm request phình ra. Cần kiểm tra gói cuối cùng và giữ allowance cho output. Các limit đo byte và tiền/token-bound là ba phép kiểm tra khác nhau.

## Direct provenance without recursive state replay

Use the existing consistent read envelope `{owner,contract,frontier,dispatches,receipts}` with at most64 distinct current-attempt dispatches plus their directly referenced current receipt rows, counted together. SQL bounds apply before materializing; no task-wide dispatch scan before this bound on v2 model/skill paths. Harness uses this envelope for prior-action lookup and frontier before planning, rather than calling task-wide `snapshot()` first. Reserve two slots for a new intent and eventual receipt. Reused IDs count once; aliases/inconsistent/missing receipt rows reject. Artifact bounds are separate. No timestamp-based historical filtering, checkpoint chains or foreign-attempt seed walk.

Separate three operations:

1. **Artifact/request validation:** closed v2 state/catalog/config/projection/raw history/request, deterministic renderer/planner and provider identity. It reads no derived current state.
2. **Direct historical proof:** for each loaded member or primary-load result actually present in a historical request's raw source, locate its original dispatch and actual receipt in the bounded envelope; validate exact parameters, owner, settled succeeded zero-charge load, `skill_call`, exact result wrapper/body/resources, original source-model dispatch/receipt and exact emitted call. The primary's original source has v2 acceptance for the same catalog/config and empty loaded state; prove that source's artifacts/request directly. No recursive call to derive all current records. Primary source accepted sequence must precede any historical request that discloses that load. Require the original source request/response evidence pair and exact call/result occurrence in the historical raw source. Two roots, foreign roots, cycles, chains through already_loaded, forged/omitted history or mismatched call/provenance refuse.
3. **Current derivation:** validate all current-attempt skill records under their own source version/state. Derive the unique primary only from succeeded primary receipts. Known already_loaded results must point directly to that primary; success/failure resource results must equal the deterministic operation authorized by their own accepted source. In-flight/Unknown/not-dispatched never create membership; malformed succeeded evidence is an integrity error. Compare candidate NEW acceptance state to this complete derivation and require its exact load call/result in raw and projected history.

For historical state, loaded membership is exactly the set of valid primary load results in that request's immutable raw history, not all loads that happen to exist now. Q0 remains empty after l0 commits. Q1 remains loaded after a later resource commits. A current derivation may observe committed membership while another operation is unresolved, but cannot authorize new intent. Historical proof of a primary never recursively validates later resource records or replays SkillsState chains. Each source response uses its exact parser (`scripted-fixture-v1` Anthropic-format fixture or frozen Nebius model), complete linkage and exact call occurrence. A native source requires succeeded effect, settled nonnegative ordinary actual units and its matching actual receipt; independently parse model/usage, require frozen envelope token bounds and actual units equal its computed charge. Billing-unknown success, malformed/token-bound-violating response or transport diagnostic cannot authorize a skill operation.

Source-history authenticity is bounded and concrete. Reconstruct the raw source from the exact initial user message `"\n".join(contract["requirements"])` and its ordered provider evidence pairs. Each pair must match one same-owner v2 accepted model dispatch's exact request reference and succeeded settled response/actual receipt; accepted sequences strictly increase, and preserve its raw parsed assistant message including opaque fields. Its own saved source messages/evidence must equal the already reconstructed prefixes. Each returned tool call must map to its ordinary deterministic dispatch ID, exact call/input/provenance identity and succeeded/failed-known settled actual receipt; append the exact canonical result artifact using native or scripted result shape and correct error flag. Apply the existing per-tool input identity rules, including `context_retrieval` projection binding, not a blanket assumption that all tools use bare call digest. Require reconstructed raw source equality, no invented/omitted/reordered/duplicated assistant, tool or evidence entries. Skills result contents additionally receive deterministic capture/source-state validation; ordinary non-skills results are validated as exact durable result bytes and call linkage, without reexecuting workspace effects or claiming their semantic correctness. Distinct records remain within the shared64 cap; use direct indexed evidence, not recursive state derivation. Historical validation examines this saved prefix and named primary proofs, not future response/result entries absent from it.

**VI:** Nếu validator của Q1 tự derive toàn bộ state hiện tại, nó gặp resource r0 rồi quay lại validate Q1 vô hạn. Cách đúng là Q1 chứng minh bằng l0 và source Q0 trực tiếp. Loaded root chỉ có một nên proof không cần đi xuyên lịch sử checkpoint hay state chain.

## Atomic acceptance, retry and concurrency

For a genuinely NEW v2 model dispatch, the public store method freezes input, validates artifacts/request/planner, obtains bounded consistent records, validates same-attempt v2-only profile and fixed catalog/config/adapter, derives state and checks exact source-history evidence. Prepare an internal canonical fingerprint of the complete bounded dispatch+receipt records. No artifact I/O occurs under the authority transaction.

In the same transaction as `context.accepted` and `dispatch.intent`, recheck current owner/lease/generation/cancellation, exact task contract and both capabilities, previous projection, task frontier, bounded record fingerprint/current referenced receipts, unresolved effects and room for two records. Compare durable state to the prevalidated records rather than trusting a caller loaded list. All failures roll back both events, intent and reservation. Any intervening heartbeat/receipt/intent fences the candidate; do not automatically rerun a model or tool effect. Existing context acceptance's event sequence and schema version are preserved accurately. Use bounded action-identity lookup for v2 just as step3 does for skill calls.

For an EXISTING dispatch ID, validate the saved manifest's historical state and exact artifacts/source prefixes, and require exact ordinary parameters and manifest/state/request equality. Do not derive a replacement state from later receipts. The store still validates current owner and exact duplicate identity, then returns duplicate before current-frontier/current-state/capacity admission for new work. Harness checks prior durable dispatch before planning, uses its saved binding/state and reconstructs the original request. Known succeeded duplicate with exact valid receipt/response returns old evidence without send; in-flight/Unknown/billing-unknown or malformed duplicate refuses reconciliation. A racing creator that wins after preflight must make the loser take this duplicate branch, never send or publish another result. Changed same-ID source/provenance/request/state conflicts.

No exact known retry republishes artifacts or adds events/cost/receipt: Harness reuses saved request/projection/raw-history/offload/state references after read-only reconstruction, without calling publication helpers; broker reuses existing result reference. A new action after load may return already_loaded pointing to the root. An exact skill retry uses its original accepted source even after a later pin and revalidates durable result; changed direct-store metadata conflicts. New model/source proof checks require current original receipt rows, never dispatch labels alone. Where a prepared fresh state races with another new state, the frontier and complete durable fingerprint make one admission win. A racing fresh preparation may have produced orphan immutable request artifacts before learning that another intent won, but it must not send or publish a tool result after receiving duplicate status.

**VI:** Retry m0 sau l0 không được sửa Q0 thành loaded[P], vì như vậy đổi request của cùng dispatch ID. Giữ Q0 cũ để đọc response cũ; sau đó replay receipt tool cũ và xây Q1 mới. CAS bảo vệ quyết định mới, không được dùng current state để viết lại quá khứ.

## Resource authority and deterministic tool results

Keep exact parent `skill_call`, six dispatch parameters, call/input digest and result wrappers. New accepted-mode broker source must be the authoritative latest successful accepted v2 model record for a new call. Validate source catalog/config, SkillsState and original primary proof, exact parsed call occurrence/linkage, durable source receipt, and both configured/durable capabilities before admission. Store `begin_skill_dispatch` performs its own version-aware preflight and carries a internally computed durable fingerprint to the transaction; the transaction rechecks current owner/frontier/latest source/receipt/capabilities and bounded evidence. A broker pin is not authority and may precede model receipt commit.

Result rules in deterministic order: wrong configured catalog raises pre-intent `stale_catalog`; wrong package yields failed-known `invalid_package` for load or `resource_denied` for read. Valid-package read without membership in the source accepted state returns `not_disclosed`, even if a load already committed later in that same response. After disclosure, require lexical exact path membership and bounds; nonmember path gives `resource_denied`, valid path with invalid offset/limit gives `bounds_exceeded`. Protocol/schema violations and source/capture/receipt integrity failures reject before intent. Stable known-operation failures use existing bounded SkillError wrapper and preserve original provenance. No traceback or host path in results.

Authorized reads use only validated captured artifact bytes. `0 <= offset <= total_size`, `1 <= limit <=8192`; strict integers, byte offsets, EOF allowed. Value exact keys remain `{catalog_digest,package_digest,path,digest,offset,total_size,size,next_offset,eof,encoding:"base64",data}` and the full ordinary `{call_id,tool,ok,value,skill_provenance}` canonical wrapper must fit65,536 bytes. A resource's bare digest or same bytes at another path confer no access. Primary load/already_loaded wrappers stay unchanged. Prepare deterministic result before intent, then publish and ordinary finish; orphan/Unknown/ACK-loss semantics stay step3. On validation, recompute successful resource and failed-known result from its original accepted source and captured bytes, not today's loaded set.

**VI:** Resource permission xét tuple catalog/package/path và request đã sinh call. Hash đúng nhưng path sai vẫn bị từ chối. Base64 giữ byte offset chính xác khi cắt giữa ký tự UTF-8; caller ghép bytes rồi mới decode.

## Explicit checkpoint boundary for this dependency step

Typed `harness_skills_v1` schema3 checkpoints, post-turn state and fresh-owner restore remain dependency step5. This step creates none. A skills-enabled Harness rejects any non-null `restored` or `pause_after_turn` before new artifact publication, intent or send. On normal completion or turn exhaustion return exactly `{status,turns,messages,evidence,checkpoint_id:null,checkpoint_status:"unsupported_skills_v1"}`. Status is `"completion_proposed"` with completed turn count for terminal/finish completion, or `"turn_budget_exhausted"` with `turns=self.max_turns` after all allowed turns; this explicit exhaustion return is new only for skills mode (disabled behavior still raises). Emit no checkpoint artifacts, records or events, including intermediate turns. Messages/evidence and durable dispatch/receipt records remain inspectable. The next step must add typed pre-request/post-turn checkpoint semantics before claiming resumable execution.

`RuntimeStore.checkpoint` checks the current attempt's dispatches transactionally and rejects if any carries a v2 skills acceptance, including when the caller supplies a legacy-looking manifest. Existing checkpoint validators/restore reject v2 skills contexts in legacy/context checkpoint formats and unknown schema3. No silently fabricated empty skills state. The same-owner exact Harness replay described above is duplicate convergence against durable intents; it is not checkpoint restore or fresh-owner recovery. Existing disabled checkpoint behavior remains unchanged.

**VI:** Không ghi checkpoint cũ chứa skills rồi hy vọng restore hiểu đúng. Kết quả trả về nói rõ chưa hỗ trợ checkpoint. Đây là ranh giới tạm thời có kiểm tra fail-closed, không phải bằng chứng recovery đã hoàn thành.

## Failure matrix and distinguishing experiments

All are proposed assertions before execution. Use disposable real SQLite records, local PostgreSQL when available/authorized, and actual native HTTP client with injected local mock transport. No paid requests. Preserve original failed controls, repair evidence and exact source hashes. Assertions should calculate expected bytes independently, not merely call the production renderer twice.

| ID | Intervention | Required observation |
|---|---|---|
| D1 accepted trace | Q0 catalog → l0 receipt → Q1 loaded → r0 → Q2 | Q0 state empty/no distinctive body; Q1 exact original load call/result/body and one loaded root; Q2 exact resource result; catalog/system/capability digest fixed while prompt/request changes |
| D2 actual send | Native mock captures three raw HTTP bodies and opaque response fields | Parse each actual body, independently canonicalize its payload and compare with the accepted request record's payload; reconstruct/hash the full native request record and match request reference/input digest. Call IDs/opaque assistant fields persist; tool schemas exact. HTTPX wire whitespace/order need not be canonical and its raw-body hash is not the request digest |
| D3 same response | Q0 emits load then resource read | Load succeeds but read fails not_disclosed; Q1 read succeeds; reading before load also denied |
| D4 authority | Wrong owner/lease/generation/capability/source/diagnostic/Unknown or stale pin | No new model/skill intent; native source positive settled charge accepted, unknown charge denied |
| D5 coherent forgery | Rehash state, body, result, source history, catalog/request/prompt/tool fields together | Authoritative receipt/call/catalog/renderer/history checks still reject; submitted loaded list alone cannot pass |
| D6 atomic race | Change frontier or receipt after preflight; interleave identical and conflicting model/skill begin | No partial acceptance/intent/reservation; identical loser uses duplicate and never sends/publishes; conflict refuses |
| D7 old retry | Restart same owner after load/resource/Q2, or lose receipt/model ACK | Reconstruct original empty Q0 and later states unchanged; no new send/event/cost/artifact for exact known work; changed same-ID state conflicts; uncertain work not replayed |
| D8 direct proof | Revalidate Q0/Q1/Q2 after later resource; two roots/cycle/foreign or chained duplicate;64/65 records | No recursive validator; direct proof succeeds only for exact originals; bounded refusal before new intent; two-slot reservation enforced |
| D9 cap/offload | Load commits then next full request exceeds cap; protected old load/resource/error result otherwise eligible | Receipt persists, no acceptance/send, protected body never offloaded; independent validator rejects forged protected offload |
| D10 resource bytes | Origin mutated, captured bytes corrupted, wrong path/digest, EOF, multibyte chunks, limit edge | Origin never reopened; corruption fails; exact base64/size/next/eof; no raw artifact access |
| D11 versions | Unconfigured/partial, broker-v1→v2, v2→disabled, mixed keys, unsupported Anthropic/capability and half schemas | Refusal before effects; old v1 evidence remains v1; disabled schema/request golden identities unchanged |
| D12 checkpoint | Restored/pause input, completion/exhaustion, direct legacy checkpoint attempt after v2 | Pre-effect refusal or explicit null/unsupported return as specified; no legacy checkpoint record; existing disabled restore regressions pass |
| D13 crash accounting | Failure before intent, after intent, after result publication, before/after receipt commit, provider intent before send | Ordinary unresolved/orphan/Unknown/ACK boundaries remain intact; no manufactured zero settlement or automatic replay |

At least three disposable defective alternatives must fail targeted tests: trust submitted loaded state; authorize read from post-load current state instead of source acceptance; drop protected load body from actual native payload. Include a provenance version-promotion or recursive-current-state defect control if implementation structure makes it a plausible failure. Focused tests, affected context/provider/protocol/skills/store/recovery suites and lint precede broader justified integration. Record exact skips and distinguish mock transport from live provider evidence.

**VI:** D2 bắt lỗi gửi thiếu body dù manifest có đủ; D3 bắt lỗi cấp quyền từ state mới thay vì request cũ; D7 bắt lỗi dùng receipt tương lai viết lại Q0. Những mutation này kiểm tra cơ chế khác nhau, không chỉ số lượng testcase.

## Tiny trace, work ownership and exit

AI-authored expected trace: captured body `Read references/checklist.md.\n` is30 UTF-8 bytes; resource `OK\n` is3. Q0 accepts state `[]`; l0 commits result and primary `[P,l0,result_ref]`; Q0 read still denies. Q1 contains exact l0 result, accepts that primary, emits offset0/limit2 read returning data `T0s=`, size2,next2,eof false. Q2 includes that result. A subsequent offset2/limit2 read returns `Cg==`, size1,next3,eof true. All success depends on captured bytes and receipts, not origin files. No checkpoint appears in this trace.

**VI:** Mốc receipt và mốc request là hai đường cắt độc lập. Body30 byte đã load sau l0 nhưng chỉ được disclosed ở Q1. Resource ba byte chia 2+1; request sau đó giữ đúng result wrapper và provenance. Đây là prediction của AI, chưa phải kết quả đo hay teach-back của Huy.

Suggested ownership after review/freeze: one integration code owner for `service/harness.py`, `storage.py`, `recovery.py`, `context.py`, `providers.py`, `skill_runtime.py` and new `skill_disclosure.py`; independent test owner for new disclosure/provider/store tests and disposable mutation controls; root for source-only demo, teaching trace, docs/context and verification record; architecture author for independent source review and review evidence. Do not concurrently edit runtime files. Existing `skills.py`/`protocol.py` require no behavior changes unless a reviewed concrete seam requires it; freeze any contract adjustment before implementation.

Root froze this contract after architecture, implementation-seam and independent testability review; immutable spec and baseline hashes are recorded before implementation. Exit requires the accepted trace and actual mock HTTP evidence, failures/retries/caps/version/checkpoint controls, independent source review, appropriate regressions and core docs updated only to measured step4 scope. Preserve the parent/broker specs, historical runs/releases, benchmark locks/population, human mastery tracker and paid hold. Provider task performance, semantic prompt-injection immunity, hostile-code isolation, mandatory old-writer enforcement, production service readiness and fresh-owner skills recovery remain unestablished.
