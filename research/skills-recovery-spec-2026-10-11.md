# Immutable skills step 5: typed checkpoint and fresh-owner recovery

Date: **2026-10-11**, Asia/Ho_Chi_Minh. Status: **FROZEN before implementation — reviewed by integration owner; not implementation evidence**. AI-authored. Parent authority is the [frozen immutable-skills design](immutable-skills-spec-2026-10-10.md); prerequisite is the [delivered step-4 disclosure contract](skills-disclosure-spec-2026-10-11.md). This specification completes the parent's R1–R4 scope. Paid/live-provider/GPU execution stays disabled. Store schema2, legacy request identities, broker-v1 evidence, historical releases and human mastery stay separate.

## Purpose, ownership and decisive trace

A checkpoint must retain two different historical cuts. Its last accepted model request describes what the model saw before its response. Its post-turn state describes which tool results subsequently committed. A fresh owner may import that state only through validated checkpoint provenance, then create a new accepted request under its own authority. Restoring data never grants execution or reconciles an external effect.

**VI:** Q0 có loaded `[]`, response gọi load, receipt l0 thành công, checkpoint có loaded `[P]`. Cả hai state đều đúng ở hai thời điểm khác nhau. Sửa Q0 thành `[P]` là viết lại lịch sử; chỉ giữ `[]` thì làm mất receipt thật.

| Object | Owner and invariant |
|---|---|
| Catalog/config/package/result bytes | Immutable scoped artifacts; validate exact bytes and bounds, never reopen origin |
| Original load and source-model records | Authority store; retain original owner, acceptance, dispatch/result/receipt identities |
| Last accepted request | Exact saved context-v2 manifest, source prefix, state, provider representation and request bytes |
| Post-turn state | Derived from checkpoint-covered successful primary load receipts plus validated seed; no submitted-state authority |
| Checkpoint acceptance | Current owner's store transaction; owner/frontier and complete evidence rechecked after artifact preflight |
| New tool authority | Fresh owner + frozen capabilities + latest successful accepted request in the fresh attempt |
| Unknown effects/billing/physical environments | Existing ledgers and explicit reconciliation; checkpoint does not alter them |

Expected experiment: owner A accepts Q0 with empty loaded state; load l0 succeeds; pause saves k0 with original Q0 and post-turn `[P,l0,result_ref]`. Retire A's controlled environment through existing trusted evidence, reopen the store, acquire owner B, reconstruct k0 without sends, then accept Q1 under B with exact l0 body and state `[P,l0,result_ref]`. A Q1 resource read succeeds from captured bytes; a direct old-source read under B fails. Q0 remains byte-identical. Repeat through owner C after a resource result and verify all original provider fields survive. This is a proposed oracle, not a measured result or Huy's prediction.

**VI:** Owner B thừa hưởng evidence, không thừa hưởng quyền của A. `load_dispatch_id` vẫn trỏ l0 của A; resource call mới phải trỏ model dispatch mới của B. Hai identity đó không được gộp.

## Exact versioned shapes and compatibility

Keep parent shapes, without a database migration or active-skills table:

1. New payload: exact legacy context-checkpoint payload keys `{schema,kind,context,messages,evidence,workspace_ref,projection_version,status}` plus `skills_after_turn`; `schema:3`, `kind:"harness_skills_v1"`, `projection_version:1`.
2. New authority manifest: exact context-checkpoint manifest keys `{artifact_ref,workspace_ref,provider_artifacts,next_turn,completion_proposed,schema,kind,context}` plus `skills_after_turn`; `schema:3`, same kind.
3. `skills_after_turn` is exactly `{state_ref,state_digest}` in both copies. `state_ref` is a closed scoped artifact reference and `state_digest` equals its digest and canonical state digest. Copies must match exactly. Use the inherited 65,536-byte state artifact bound.
4. `context` retains exactly `{acceptance,dispatch_id,source_message_count,source_evidence_count,checkpoint_history_digest,checkpoint_evidence_digest}`. Its acceptance remains `context_schema:2`, using the original saved pre-request SkillsState. Do not copy post-turn state into it.
5. `SkillsState` retains exact `{schema:1,catalog_ref,catalog_digest,config_ref,config_digest,loaded,source_checkpoint}`. `loaded` remains zero or one direct primary `{package_digest,load_dispatch_id,result_ref}`. Fresh execution uses `source_checkpoint:null`; every request and checkpoint state within a restored attempt retains the imported seed checkpoint ID. When another attempt restores the new checkpoint, its seed ID becomes that new checkpoint ID. A checkpoint never points to its own not-yet-created ID.
6. Each restored request's context manifest carries the same `source_checkpoint` as its SkillsState and `restored_from_projection_id` equal to that seed checkpoint's last acceptance projection ID. Both are null in a fresh attempt. The new attempt's first `expected_previous_projection_id` is null; subsequent requests use only that attempt's previous acceptance.

Typed dispatch must be explicit. Schema3 + wrong/missing kind, half-populated skills/context keys, booleans masquerading as versions/turn counts, extra keys and unknown versions reject. Schema1 legacy and schema2 `harness_context_v1` remain skills-disabled; schema3 cannot restore with skills disabled, and legacy/context checkpoints cannot enter accepted-skills mode. Broker-v1 cannot be promoted. Preserve disabled/default golden requests and historical payloads.

**VI:** Schema3 chỉ là version checkpoint payload. Database vẫn schema2. State ghi seed checkpoint đã tồn tại, không thể ghi ID của checkpoint đang được tính hash.

## Validation algorithm and bounded provenance

Separate pure byte/shape reconstruction from authoritative record validation. Artifact-only validation may recognize a structurally valid non-null checkpoint ID; it must never certify its authority. Caller-supplied `restored` dictionaries, in-memory loaded lists and broker pins are untrusted claims. On skills restore, resolve `source_checkpoint` again through the store and compare/reconstruct the returned values before using them. Never bypass this because a caller already invoked `restore_checkpoint`.

Use a bounded evidence bundle with the current owner records, directly referenced historical model/tool dispatches and their original receipts, and referenced checkpoint rows. Historical records retain their own owners; they are not relabeled with the caller owner. Every historical owner must agree with its authoritative attempt, tenant/task, frozen contract and task generation. Model/source helpers must validate a specified historical owner without applying that owner's expired current lease. Only new admission uses `_owner` for current authority.

Collect with bounded exact lookups and bounded per-attempt scans; do not load the whole task and only then apply a limit. Reuse a shared visited set keyed by `(record_kind, scoped_record_id)` and a limit of **64 distinct provenance records**, including dispatches, receipts and any referenced checkpoint rows. Never count the same row twice. Reject cycles or a 65th row before new acceptance/intent. Maintain the existing current-attempt dispatch+receipt bound and reserve two additional rows before a new dispatch. A new checkpoint must itself fit any proof that will reference it; reject at the bound rather than silently trimming evidence. Opaque artifact bytes have their inherited byte caps and do not count as database records. Task/owner authority guard reads are not provenance-chain hops.

Use an iterative worklist and chronological transcript reconstruction, with memoized byte validation. Do **not** implement `derive_state -> restore_checkpoint -> derive_state` recursion, recursively chase `already_loaded`, or use current loaded state to validate an earlier accepted request. Checkpoint ancestors are validated against their own recorded cut; they cannot contribute receipts after that cut. A direct root points to the original succeeded load and its source-model acceptance; `already_loaded` always points directly to that root and is never a new membership entry.

For every retained provider evidence pair, find exactly one accepted model dispatch, validate its original owner/parameters/context-v2 acceptance, exact request/result references, succeeded effect, settled charge and matching immutable receipt. Reconstruct the response using the supported scripted or native Nebius parser. Validate raw assistant fields, call IDs/order and exact result bytes against original tool dispatches/receipts; append those original protocol objects without normalization. Each accepted request's source history/evidence is exactly the prior reconstructed prefix. Its loaded state equals what was durable and disclosed at that point, respecting its validated seed and current-attempt receipts. Source workspace identity remains the accepted source's identity; the newer checkpoint workspace is separately validated.

For each primary load, check original `skill_call`, exact source call occurrence and input identity, original accepted catalog/config, succeeded zero-charge receipt, deterministic captured body/resource descriptor wrapper, and exact history occurrence. The primary's source acceptance is empty for the one-package profile. Reject two roots, missing/invented/omitted root, wrong result/tool/call/owner, foreign scope, chained duplicate, diagnostic response, Unknown/unsettled source, or coherent rehashes unsupported by authoritative records.

For a checkpoint, verify the original acceptance against its authoritative dispatch and reconstruct its request using that acceptance's saved pre-response state. Separately extend the source prefix by exactly that response and every matching result to the retained post-turn history, then derive `skills_after_turn`. `next_turn == len(evidence)`; the last acceptance adds exactly one provider evidence pair to its source evidence prefix. Provider linkage must be complete; checkpoints cannot cut a tool-call batch. All current checkpoint-owner dispatches at acceptance must be represented/known and covered by the checkpoint frontier. A valid failed-known tool result may be retained; unresolved/Unknown or unsettled covered evidence may not certify a skills checkpoint.

**VI:** Đọc lịch sử theo thứ tự giúp kiểm tra Q0 trước l0, Q1 sau l0. Proof đi thẳng đến receipt gốc nên restore nhiều lần không tạo dây `already_loaded` dài vô hạn. Limit64 là fail-closed; không phải chính sách xóa lịch sử để tiếp tục.

## Store transaction, restore and fresh authority

Before `RuntimeStore.checkpoint`, publish immutable workspace/state/payload artifacts and perform bounded artifact/provenance preflight outside the authority transaction. Carry an internally computed fingerprint of every referenced authoritative record and each relevant attempt's full bounded dispatch frontier. Inside one transaction: validate current owner/contract/generation/deadline, re-read those records/frontiers, compare the fingerprint, require the last accepted model and post-turn state to remain exact, then accept the schema3 checkpoint/event atomically. A receipt, intent, heartbeat/frontier change, owner replacement or altered seed between preflight and commit fences the candidate. No artifact read, model send or tool effect inside the transaction. Orphan artifacts confer no checkpoint or membership authority.

Keep the existing schema3 guard behavior for legacy-looking manifests: an attempt with context-v2 acceptance may checkpoint only through the typed skills validator. Simply deleting `skills checkpoints are unsupported` is insufficient. A direct store caller cannot bypass post-turn validation by supplying a schema1/2 manifest. An exact already accepted checkpoint can be reused read-only; never create another event solely because the Harness retried known work.

`restore_checkpoint` validates the authoritative row's scope, contract/generation, original acceptance, both state cuts, full provider receipts, workspace and post-checkpoint frontier. Any dispatch from its owner after that checkpoint, including a known read-only operation, forbids rewind; in-flight/Unknown blocks it independently. Validate ancestor cuts without confusing their later legitimate descendant continuation with effects that existed before descendant checkpoint acceptance. Read-only restore emits no events/artifacts, sends nothing, and changes no budget, receipts, generation, slot or retirement record.

For fresh model/skill admission, preflight imports historical evidence only through the validated seed. The final store transaction rechecks the seed and all historical proof/frontiers as well as current-owner records. This closes the race where an old owner adds a post-checkpoint dispatch between restore validation and new admission. Old original receipt rows must still exist and match. Frozen capabilities must be present both in current configured broker and durable task contract; an old receipt cannot supply a missing capability. Fresh resource source must be the latest succeeded, settled accepted model dispatch in the current attempt, with the loaded primary in that request's accepted state.

Acquiring an owner remains an explicit existing store operation after required retirement/reconciliation. This slice does not automatically kill old environments, settle bills or replace active attempts. Cancellation/generation drift, expired current owner, changed contract/catalog/config/adapter/tool/renderer, or missing artifacts refuse before a new model/tool intent. Actual native request bytes use the existing supported reconstruction/build path and `include_skills=True`; no discovery, planner or new model invocation substitutes for reconstruction of old accepted bytes.

**VI:** Có hai lần kiểm tra: đọc artifact ngoài transaction để tránh giữ lock lâu, rồi so fingerprint/frontier trong transaction để chặn race. Restore không được “sửa” Unknown thành zero charge chỉ vì chưa thấy response.

## Harness behavior and crash semantics

Enable `pause_after_turn` only after typed checkpoint support is active. After each fully recorded turn, write/reuse schema3 checkpoint with post-turn state. A pause returns `status:"paused"` and real `checkpoint_id`; completion returns `completion_proposed` and real ID. Retain skills-mode explicit `turn_budget_exhausted` return, backed by the last fully recorded checkpoint (`payload.status:"checkpointed"`, `completion_proposed:false`); do not introduce an unsupported payload status. Restoring a completion checkpoint returns the existing completion proposal with no new send/intent/checkpoint. Turn counts remain cumulative across owners; a restored exhausted checkpoint cannot silently reset the budget.

Known same-ID model and tool retries retain their saved original source/state/request/result/provenance, even after a later receipt, pin or checkpoint. Reuse saved artifact references and accepted checkpoint; no artifact publication, event, cost, result or network send for exact known work. A racing new creator that discovers a duplicate follows the same read-only branch. Unknown/in-flight/unsettled duplicates refuse reconciliation. Changed identity/provenance/state under the same ID conflicts.

| Crash boundary | Required retained outcome |
|---|---|
| Before intent | No authoritative effect; possible orphan immutable artifacts |
| Tool intent before terminal receipt | Unresolved dispatch, no membership, no automatic replay |
| Load result published but receipt absent | Orphan result; no loaded state/checkpoint |
| Load receipt committed before checkpoint | Membership remains durable; failure to checkpoint cannot erase it or rewind effects |
| Checkpoint artifact before checkpoint acceptance | Orphan checkpoint payload; never imported as authority |
| Checkpoint accepted, ACK lost | Reopen/reuse exact checkpoint and receipt; no duplicate event |
| New model acceptance/intent before send | In-flight reservation remains; no inferred no-send or free retry |
| Request cap exceeded after load/restore | Existing load/seed remains; no new acceptance/intent/send; protected body is retained |

**VI:** “Request quá lớn” là lỗi admission của Q1; không phải lý do undo l0. Checkpoint proposal chỉ trở thành checkpoint khi store commit, giống result chỉ trở thành load khi receipt commit.

## Acceptance tests and defective controls

Independent tests must create authoritative records and assert independently calculated expected bytes, identities and ledgers. Actual native HTTPX mock transport captures requests; no paid calls. Exercise SQLite and existing opt-in local PostgreSQL for transaction/race gates. Retain artifacts and source hashes under a new dated run directory.

| ID | Intervention and required observation |
|---|---|
| R01 pre-disclosure | Q0 empty -> l0 -> k0; k0 accepted state empty, post-state one root. Fresh B Q1 carries exact original body, B owner/new frontier, original A root. Origin mutation changes nothing. |
| R02 successive owners | Restore after resource read, then again under C; all native opaque fields/tool IDs/result bytes/provider pairs preserved. Direct root remains l0, state seed ID advances per attempt only. |
| R03 authority | Stale/expired A and forged B owner; missing configured/durable caps; B pinned to A model; mutated adapter/catalog/config/renderer; all reject before new intent/send. Positive B Q1 then read must succeed. |
| R04 coherent forgery | Rehash checkpoint/state/request/history together while omitting/inventing load, altering result/body/path/call/source/receipt/owner, changing both post-state copies, or replacing raw provider fields; authoritative proof rejects. |
| R05 frontier race | Inject owner/receipt/intent/frontier change between preflight and checkpoint or first fresh admission; no checkpoint/acceptance/intent/partial budget mutation. Include old-attempt post-checkpoint read race. |
| R06 Unknown accounting | In-flight, Unknown, settled bill+Unknown effect, known effect+unsettled bill, diagnostic HTTP response, lost model/receipt ACK and late trusted settlement. Restore/retry never clears liabilities or replays unresolved work; late settlement applies once. |
| R07 direct bound | Shared visited record64/65; cycle, two roots, chained already_loaded, foreign scope and missing original row.64 valid bounded proof accepted;65/cycle reject before new intent. New dispatch leaves two-row room. |
| R08 typed boundary | Schema1/2 -> skills, schema3 -> disabled, broker-v1 -> accepted, half/unknown/bool schema, same-version extra keys, direct legacy checkpoint after v2 reject. Existing legacy/context disabled goldens pass. |
| R09 exact replay | Same owner full known Harness replay after checkpoint; repeated restore; completed restore; same dispatch with changed metadata; racing identical creation. Exact known paths add zero sends/artifacts/events/cost; conflicts/uncertainty refuse. |
| R10 faults and bounds | Fail result, state, workspace or checkpoint publication/commit independently. Cap overflow after committed load and after restore; body never offloaded/dropped, load retained, no new request. Turn exhaustion and complete/pause semantics exact. |
| R11 native send | Capture B's actual mock HTTP payload, independently canonicalize and match accepted request record; original load/resource results and native opaque fields present. Reconstruct old Q0 without sending it. |
| R12 clean process boundary | Close all source store/adapter objects, reopen persisted artifacts/DB, retire/reacquire through supported APIs, then resume. Separately prove unresolved physical environment still blocks replacement. |

At least three disposable defective implementations must fail: (1) use post-turn state to reconstruct old Q0, (2) trust submitted restored/loaded state or skip original receipt proof, (3) treat old source receipt as fresh resource authority. Also target a plausible recursion/65-record defect and removal of historical-frontier transaction recheck when feasible. These test mechanisms, not line coverage.

**VI:** R01 phân biệt hai mốc thời gian; R03 phân biệt dữ liệu với quyền; R05 phân biệt preflight với atomic acceptance. Một runtime từ chối mọi restore sẽ fail positive R01/R02, dù pass các negative test.

## Exact implementation seams and ownership

Minimal implementation API proposal (internal names may be consolidated without changing the contract):

```python
# Existing public signatures remain compatible.
restore_checkpoint(store, artifacts, tenant_id, task_id, checkpoint_id) -> dict
RuntimeStore.checkpoint(owner, manifest) -> dict

# New bounded store reader; no artifacts or external effects in its transaction.
RuntimeStore.read_skill_proof(owner, *, source_checkpoint=None) -> dict
# Returns current owner/contract/frontier, uniquely keyed dispatch/receipt/checkpoint
# rows, per-owner dispatch frontiers, and a canonical durable fingerprint.
# source_checkpoint is explicit on first import; later use must match that attempt.

# Pure byte and closed-schema validation; deliberately grants no authority.
validate_skills_checkpoint_artifacts(artifacts, tenant, task, manifest, payload) -> dict

# Validates complete bounded authoritative proof and returns reconstructed data.
validate_skills_checkpoint(proof, artifacts, checkpoint) -> dict
# Result extends legacy restore data with skills_after_turn and validated SkillsState.
# Never expose a boolean "trusted" flag that bypasses later store validation.

# Existing helpers accept an optional already collected, validated seed/proof;
# absence means fresh mode, never an inferred arbitrary previous attempt.
derive_skills_state(store, artifacts, owner, capture, config, *, source_checkpoint=None) -> dict
```

The first reader can collect the bounded checkpoint chain iteratively by exact IDs, then gather its named owner records/frontiers and receipt rows. A second read of the same selected record set inside admission computes the fingerprint again. Artifact validation and protocol reconstruction occur outside that transaction. Use one proof object per operation, not independently reset64-record budgets in each nested helper. Do not add a public network recovery endpoint in this slice.

**VI:** `source_checkpoint` là input để store tìm evidence, không phải dấu “đã tin”. Fingerprint được tạo nội bộ từ row thật; caller không thể tự viết fingerprint rồi bỏ qua kiểm tra receipt.

Verified against source on 2026-10-11 before implementation; line numbers may move afterward:

| File/function | Required change |
|---|---|
| [Harness.run](../service/harness.py#L183), nested `save_checkpoint` at304 | Typed skills save/restore/pause/completion/exhaustion; authoritative restored-data revalidation; preserve two state cuts, seed IDs and exact retry artifacts |
| [validate_context_manifest](../service/recovery.py#L116) | Recognize consistent non-null skills lineage structurally; keep authority validation separate |
| [validate_context_checkpoint](../service/recovery.py#L271), [restore_checkpoint](../service/recovery.py#L34), [validate_checkpoint_dispatches](../service/recovery.py#L367) | Explicit schema dispatch; closed schema3, post-state validation, historical/current owner separation, exact provider receipts and bounded restore proof |
| [state_value/validate_state_artifacts](../service/skill_disclosure.py#L31) | Closed non-null seed ID support without inventing authority |
| [_model/_primary/_expected](../service/skill_disclosure.py#L152), [validate_history/derive_from_records](../service/skill_disclosure.py#L322) | Historical original-owner proof, direct primary references, iterative seeded prefix reconstruction; no current-state rewrite of old request |
| [preflight_model/preflight_skill](../service/skill_disclosure.py#L449), [_reuse/execute_skill](../service/skill_disclosure.py#L479) | Full bounded imported proof/fingerprint; latest fresh source authority; no implicit replay or source promotion |
| [read_skill_records](../service/storage.py#L741) and new internal bounded proof reader | Read original referenced rows/receipts/checkpoints under one consistent read; exact scope, bounded queries and shared visited budget |
| [begin_projected_dispatch](../service/storage.py#L648), [_begin_dispatch](../service/storage.py#L781), [checkpoint](../service/storage.py#L1260) | Fingerprint all imported evidence/frontiers in transaction; explicit typed gate, durable owner/caps/current seed; no schema/table change |
| New `service/skill_recovery.py` if useful | Isolate bounded evidence collection/reconstruction to avoid recovery/disclosure import recursion; no second mutable authority |
| New `tests/test_skills_recovery.py`, `tests/test_skills_recovery_store.py` | Independent contract tests above; retain affected disclosure/context/protocol/Unknown/recovery regressions |
| New `scripts/skills_recovery_demo.py` | Machine-readable two-owner trace and exact request/receipt/checkpoint IDs; local scripted or mock transport only |

One integration owner edits runtime files. Independent oracle/test owner works from this specification before inspecting candidate code. Final reviewer inspects source and runs adversarial controls; root integrates source-bound verification, runbook/H0 reading trace and coverage updates only after actual evidence. This document proposes semantics; any incompatible adjustment must be recorded before implementation. No learning tracker completion follows from AI delivery.

**VI:** Spec là contract để code và test độc lập gặp nhau. Đường đọc H0 sẽ dùng l0/Q0/k0/Q1 thật sau khi chạy; chưa được ghi “demonstrated” từ trace dự kiến ở đây.
