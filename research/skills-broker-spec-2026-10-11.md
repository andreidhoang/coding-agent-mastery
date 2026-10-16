# Broker-controlled skill loading and receipt-derived state

Date: **2026-10-11**, Asia/Ho_Chi_Minh. Status: **FROZEN BEFORE IMPLEMENTATION — independently approved by Astra**. This specializes dependency step3 of [the original frozen design](immutable-skills-spec-2026-10-10.md), following [delivered immutable capture](immutable-skills-capture-spec-2026-10-11.md). Paid execution stays disabled. No promo/account information is stored or used by this component.

## Purpose, scope and invariant

Skill bytes are stable after capture, but bytes alone cannot prove a load committed. Reuse the existing ownership, dispatch intent, immutable result and receipt boundary. For package P and attempt A:

`loaded(P,A)` iff exactly one validated primary `load_skill` dispatch in A has a matching durable succeeded receipt, settled zero charge, exact deterministic result and valid source-response provenance.

An artifact without that receipt is an orphan. A requested or uncertain load is not loaded. A second call may point directly to the primary load but cannot create a second membership root. No skill text or metadata changes the frozen capability set.

**VI:** Có ba vật khác nhau: lời gọi tool, file result, và receipt commit. Chỉ receipt đúng gắn với đúng bytes/result/source mới chứng minh load đã xong. Nếu mất ACK sau commit, retry phải đọc evidence cũ; chạy lại sẽ che mất ranh giới failure cần học.

This first broker slice is an **offline scripted control-plane seam**, not the full skills-aware Harness. Existing context-v1 accepted requests cannot prove accepted catalog or loaded-state disclosure. A trusted caller explicitly supplies a validated capture/config to the broker. Supported source is an ordinary successful `model.scripted` context-v1 dispatch, with `scripted-fixture-v1` response and existing context adapter. This proves response/call provenance, not that a catalog was advertised to a live model. Reject native/Anthropic source profiles here. The later step4 must establish versioned catalog/tool/request identities and native mock HTTP behavior; it cannot silently import these broker-only records as fully accepted SkillsState. Step5 adds typed checkpoint/fresh-owner recovery. The original full design remains unchanged.

`read_skill_resource` is schema-known and capability-gated but returns a bounded `not_disclosed` failed-known result for valid-package calls on this configured broker path, including immediately after load. Pure capture helpers remain available to trusted control-plane code; they do not become resource-authority APIs. No provider call, new Harness loop option, prompt renderer, context-v2 acceptance, checkpoint type, restored seed, installation or script execution is implemented here.

## Owners and compatibility

- RuntimeStore schema2 and six-field dispatch parameters stay intact. Versioned `skill_call` is sibling metadata, compared during duplicate checks. No active-state table or pointer is added.
- Artifact storage owns scoped immutable bytes. Existing captured profile/config/limits and parser pin remain unchanged. Ordinary `finish_dispatch` owns effect/result/receipt commit; billing remains zero for these data tools.
- The broker owns the configured selection and validates capabilities against both its own constructor list and the actual frozen task contract. Both skills tools must already be in both sets to opt in.
- The latest accepted source response owns new-call provenance; current owner fencing and DB transaction own permission to commit a new intent. Exact known retries can read their old source/result under the same still-valid owner, even after a later model acceptance. No retry grants new execution authority.
- Receipt derivation owns only a detached, ephemeral result named `broker_skill_loads_v1`. It is not the future accepted SkillsState. Human H0–H15 evidence remains unchanged.

The optional broker constructor adds keyword-only `skills_capture=None, skills_config=None` after existing arguments. Both absent preserves current behavior; only one supplied refuses. Freeze deep copies and validate selection. No discovery of user's installed skills. Existing `ToolBroker.pin_context(dispatch)` remains the source pin interface; the skills path refreshes authoritative records when executing, because pinning can precede model receipt commit. All new source logic belongs in `service/skill_runtime.py` where useful; avoid splitting unrelated storage/controller behavior.

Protocol adds strict ToolCall definitions for `load_skill(catalog_digest:str,package_digest:str)` and `read_skill_resource(catalog_digest:str,package_digest:str,path:str,offset:int,limit:int)`. `tool_schemas(..., include_skills:bool=False)` only advertises them when explicitly requested; legacy default and context-only schema bytes remain identical. No provider adapter requests this option in this slice. Existing exact key/type and argument bounds apply; booleans are not integers. Reconstruct/validate incoming ToolCall arguments at execution because its nested dict is mutable. An unconfigured broker refuses either skills tool before any ordinary intent; recognizing a wire shape does not opt in the existing Harness.

## Frozen data and read APIs

`skill_call` exact keys, from the parent contract:

`{schema:1,operation,catalog_digest,package_digest,path,source_model_dispatch_id,source_projection_id,source_accepted_sequence}`

Operation is `load` or `read_resource`; path null iff load. Lowercase64-hex digests, bounded valid identities, positive strict accepted sequence, exact integer schema. Intent input digest is `D({call_digest:call.digest,skill_call})`. Call/action/dispatch/receipt ID generation preserves the ordinary broker convention. No overloaded capability/contract digest.

New bounded read seam:

`RuntimeStore.read_skill_records(owner) -> {owner,contract,frontier,dispatches,receipts}`

It uses one consistent DB read, scoped to the supplied attempt/tenant/task, returning detached data. `receipts` is a list of the current directly referenced receipt rows (unique by receipt identity), never inferred from dispatch labels. Include all attempt dispatches conservatively; source records cannot be hidden by filtering only successful loads. A bound of **64 distinct dispatch and directly referenced receipt records combined** applies, with bounded SQL fetch before materialization. The task/owner/frontier envelope is not a provenance record; captured artifact byte bounds remain separate. Old overwritten receipt IDs are not followed recursively. No prior attempts, checkpoint recursion or arbitrary caller seeds. The read validates owner structure and scoped attempt identity but does not require a live lease or grant authority; `_begin_dispatch` still fences owners. Reject dangling/foreign receipt references or inconsistent duplicated IDs. No source/result artifacts are fetched inside a RuntimeStore authority transaction.

`derive_loaded_skills(store,artifacts,owner,capture,config)` is public from `service.skill_runtime` and returns exactly:

`{schema:1,kind:"broker_skill_loads_v1",catalog_ref,catalog_digest,config_ref,config_digest,loaded,source_checkpoint:null}`

`loaded` is empty or one `{package_digest,load_dispatch_id,result_ref}`. Re-derive every time; never trust a caller-supplied loaded list. All skills-bearing records in the current attempt must bind the same supplied catalog; contradictory catalogs are rejected, not filtered away. Current capture/config artifacts validate through the existing immutable helper. Successful primary result exact bytes, call identity/input digest, current matching receipt, source accepted dispatch identity, response tool call occurrence and source context/history linkage must all validate. Failed-known/not-dispatched/Unknown/in-flight/missing-result records never create membership. Validate closed skill metadata and record/receipt consistency even when no membership is created. Known failure results must match the deterministic rejection for that exact source call; forged error codes cannot become reusable receipts. A succeeded resource record is invalid in this profile. A known succeeded record with missing/malformed result or mismatched receipt is integrity failure, not silently ignored evidence. Derivation can still describe already committed primary membership while an unrelated later operation is unresolved; it grants no permission to continue.

Already-loaded records point **directly** to the unique primary `loaded` dispatch. Validate their exact wrapper and source call just like primary records. Cycles, pointing to another `already_loaded`, foreign/missing roots, two primary roots, malformed skill metadata and a 65th provenance record fail. Bounds refuse new work; they never truncate evidence or unload a committed primary. Repeated calls cannot build a recursive chain. Restored seeds remain unsupported.

New intent seam:

`RuntimeStore.begin_skill_dispatch(owner,action_id,dispatch_id,call_digest,skill_call,expected_frontier)`

It validates metadata and computes the normal kind/input digest/zero bound, then routes `_begin_dispatch(..., skill_call=..., skill_frontier=...)`. The latter compares sibling metadata for duplicates and validates skills-specific invariants whenever metadata is supplied; ordinary begin paths cannot accidentally discard it. New intent transaction rechecks current owner, both durable capabilities, latest accepted successful scripted source and matching receipt, projection/sequence/owner binding, and exact task frontier `{service_incarnation,sequence}` from the validated read. It refuses any unresolved current-attempt dispatch and requires room for the new intent plus its eventual receipt within64 records. A stale derivation/frontier cannot create a parallel second primary. New receipt/heartbeat/model events after preparation fence the new intent; caller may start a fresh decision, but the broker does not automatically rerun effects. Exact existing duplicates are checked after current-owner validation and before latest-source/frontier/capacity requirements; changed intent or provenance conflicts.

## Source validation and results

Validate source acceptance against durable owner/input/request and the existing `validate_context_manifest` checks. Validate closed reference scope/type/size/digest with bounded artifact reads. Retained provider response uses the existing2,000,000-byte decoder cap; source/raw context helpers retain their existing bounded profile. Parse response through the scripted/Anthropic-message parser with exact model `scripted-fixture-v1`. Validate source messages plus returned assistant/tool batch linkage and require one exact `ToolCall` occurrence (ID/name/arguments), not merely a recognized tool name. Diagnostic transport-error artifacts, arbitrary same-task dispatches, missing/malformed result/receipt, failed or Unknown model effects, native provider profiles and stale pins for new actions refuse before intent. A new broker cannot widen authority by supplying a broader capabilities list.

Broker duplicate lookup uses deterministic attempt/call ID first, recovers the original durable `skill_call` rather than regenerating it from a newer pin, and verifies the supplied call digest against that stored provenance. Changed call content conflicts; the direct store API also conflicts on changed supplied provenance. Known duplicate retrieval revalidates its original source, receipt/result, deterministic wrapper and captured artifacts; do not use unchecked `get_json` fast paths. A failed-known duplicate reuses its exact bounded error result and validates its provenance/receipt/shape. Unresolved duplicate, or known effect without durable result, refuses without a new intent, artifact or receipt. ACK loss after a committed receipt returns the original result on retry. Revalidation may read immutable evidence but must not republish/re-execute.

Primary successful result is exactly the parent's ordinary wrapper `{call_id,tool:"load_skill",ok:true,value,skill_provenance}` with value:

`{schema:1,status:"loaded",catalog_digest,package_digest,body,body_digest,resources,source_model_dispatch_id}`

Body is exact captured UTF-8 text; resources are sorted `{path,digest,size}` from the captured manifest. `skill_provenance` equals `skill_call`. New call after loaded returns exact value `{schema:1,status:"already_loaded",catalog_digest,package_digest,load_dispatch_id}` pointing to the primary. Full canonical wrapper <=65,536 bytes, checked before publication/intent. A requested catalog digest differing from the configured catalog is pre-intent `stale_catalog`, so no mismatched-catalog failure record poisons this fixed selection. For a valid authorized call whose deterministic operation rejects (wrong package under the same catalog, or not_disclosed), use exact failed-known wrapper `{call_id,tool,ok:false,error_type:"SkillError",message:<stable_code>,skill_provenance}`; stable codes are the parent list. Wrong package yields `invalid_package` for load and `resource_denied` for resource; a valid package resource call yields `not_disclosed` without returning a resource chunk. Authorization/source/owner/integrity failures may raise before intent; do not manufacture a successful/failed operation receipt for work never admitted. Malformed capture/config or oversized prepared wrapper refuses before intent.

Prepare/validate deterministic result bytes before intent, without publishing that result. Commit ordinary intent, publish canonical result and call ordinary `finish_dispatch`. Publication failure leaves unresolved intent, including a failure raised after bytes were written but before the caller received the reference. Result published but receipt not committed leaves an orphan and unresolved intent. Do not catch a lost receipt ACK and overwrite it with a failed/Unknown receipt; reload durable state on explicit retry. Errors injected before/after receipt commit must preserve these distinctions. Any external I/O remains outside store authority transactions.

## Distinguishing experiments and exit

Use one authored package and disposable SQLite stores with real context-v1 acceptance plus scripted response/ordinary model receipt. No simulated in-memory receipt substitutes. Derive expected results independently in tests; do not rely only on implementation renderers. Optional local PostgreSQL verification uses already-authorized disposable local infrastructure only; not required to invent deployment evidence.

| ID | Experiment | Required distinction |
|---|---|---|
| B1 | Valid scripted source emits load; captured source folder then changes | Deterministic captured body and resources, one primary membership, frozen capabilities unchanged |
| B2 | Wrong capabilities, source/owner/scope/profile/call/linkage, diagnostic or uncertain source | No new intent or loaded state; supplied capability list cannot widen task contract |
| B3 | Fail preflight, intent commit, result publication, receipt before commit, receipt after commit/ACK | No partial state before receipt; unresolved/orphan retained; ACK retry returns exact committed bytes |
| B4 | Exact duplicate, changed same-ID arguments/provenance, new call after load, unresolved duplicate | Exact retry has no new event/cost/artifact; changed identity conflicts; direct already_loaded root only; no auto-rerun |
| B5 | Rehashed body/resource/provenance/result forgery, missing receipt, two roots, cross-attempt or cyclic duplicate | State derivation refuses fabricated/ambiguous membership |
| B6 | Same-response and later resource calls after load, without future accepted disclosure | Bounded failed-known not_disclosed result; no resource bytes returned |
| B7 | Race another receipt/intent/heartbeat after derivation, parallel primary preparations | Frontier refusal before second new intent; no competing roots admitted |
| B8 | Exact cap, first record beyond64, full escaped wrapper bound, sanitized parser/filesystem failure | Bounded refusal without truncation or private exception context |
| B9 | Disabled feature and legacy default/context-only tool schemas | Existing behavior and byte identities preserved; no opt-in in Harness/providers/recovery |

Freeze this document and baseline source hashes after independent Astra review, before Sol implementation. Separate code and test write ownership. Preserve failed experiments and repairs; independent review includes plausible flawed alternatives or distinguishing fault controls. Run focused new tests and affected protocol/broker/storage/context/recovery suites with appropriate local integrations, then lint; broaden if changes justify. Record source before/after and exact skips/limits. Reconcile core docs, source-reading trace, coverage, decisions and current context only to this delivered scope. Historical specs/releases/runs, benchmark population/locks, human tracker, hackathon priorities and paid hold remain unchanged.

**VI:** Phép thử quan trọng nhất là cắt đúng ranh giới: artifact đã tồn tại nhưng receipt chưa commit thì loaded vẫn rỗng; receipt đã commit mà caller chưa nhận ACK thì retry phải hội tụ về một load duy nhất. Đây là bằng chứng cơ chế, chưa phải live-model usefulness, accepted disclosure hay phục hồi owner mới.
