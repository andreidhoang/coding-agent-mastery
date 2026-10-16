# Failure evidence and regression adapter — engineering contract

**Date:** 2026-10-10. **Status:** frozen by the coordinating agent before production coding; subsequent contract changes require a dated addendum and a new freeze record. AI-authored architecture, not implementation or human mastery evidence. Scope: one bounded local RuntimeStore task capture, exact failed verifications and currently Unknown dispatches, immutable development regression proposals, and separate reviews. Paid execution remains disabled.

## Purpose and ownership

A committed failure is an observation about particular bytes and an execution history. A regression is a repeatable check of an invariant implicated by that observation. This slice preserves the former and checks bounded data controls for the latter. It does not run candidate code or claim that a candidate repair succeeded. The two initial predicates exercise adapter invariants: verification identity binding and Unknown accounting retention. Label a true control result “predicate satisfied.” A passing predicate is never runtime acceptance, a grader result, or evidence of live-model quality.

**VI:** Verifier fail cho cây A là sự kiện đã xảy ra. Fixture đổi digest A thành B là phép thử xem adapter có bắt attribution sai không; nó không chứng minh chương trình B đã sửa lỗi. Tách hai điều này để một test dữ liệu không trở thành “task accepted”.

| Component | Owner and obligation | Bounded source change |
|---|---|---|
| Source capture | RuntimeStore supplies a consistent read of committed task state/history; no authority changes | Append public read-only helper at the end of RuntimeStore in `service/storage.py`, private read helpers if necessary; preserve existing anchors |
| Evidence projection | `evals/evidence.py` validates source scope, coverage, joins, artifacts, accounting and lineage; owns immutable evidence | New module only |
| Regression proposal and review | `evals/regressions.py` owns a fixed predicate registry, immutable fixture/case/review identities | New module only |
| Source bytes | Existing scoped artifact store; hashes establish byte identity, not provenance/authentication | Reuse `service/artifacts.py` unchanged |
| Assignment and acceptance | Existing FrozenManifest and analyzer remain owners of assigned populations and outcomes | No analyzer/outcome adapter; no denominator mutation |

No RuntimeStore schema/mutator change, provider call, retry, execution/replay, training export, held-out promotion, GPU/CPU acceptance, scheduler, source-file import, or arbitrary code predicate. `record_verification`, `publish_review`, `record_review`, billing settlement and environment creation are never called by these modules. Imported records are data; reviews convey a declared actor, not authenticated human identity.

**VI:** RuntimeStore vẫn giữ quyền quyết định; adapter chỉ đọc. Đọc JSON có hash đúng không chứng minh người gửi là verifier. Lời khai reviewer_kind=human cũng không tự xác thực con người.

## Inspected source and stable-read decision

Inspected current [read transaction](../service/storage.py#L229), [event construction](../service/storage.py#L293), [budget derivation](../service/storage.py#L371), [dispatch settlement](../service/storage.py#L701), [snapshot shape](../service/storage.py#L1065), [verification record](../service/storage.py#L1224), [terminal failure](../service/storage.py#L1574), [artifact identity](../service/artifacts.py#L15), [manifest identity](../evals/manifest.py#L179), [candidate construction](../service/integration.py#L25), and [actual verifier output](../service/verification.py#L78). The [research audit proposal](codebase-audit-2026-10-10-research.md#smallest-next-adapter-contract--proposal-not-implementation) supplies the scope; this document resolves its previously open implementation choices.

One existing `_read()` connection provides SQLite `BEGIN` or PostgreSQL `REPEATABLE READ`. All authority/task/table/event reads must use that same connection. Public `snapshot()` then `events()` on separate transactions is insufficient. SQLite readers see a stable transaction view and PostgreSQL Repeatable Read keeps one transaction snapshot; primary documentation checked by root 2026-10-10: [SQLite isolation](https://www.sqlite.org/isolation.html), [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html). These guarantees cover supported cooperating stores, not a hostile database administrator or forged exported JSON. Artifact reads occur after the DB transaction has rolled back; immutable hash verification detects deletion/change without pretending DB and artifact storage share a transaction.

**VI:** Ví dụ capture thấy frontier=20 thì cả dispatch state và events phải là cùng ảnh DB đó. Event21 xuất hiện sau không được chen vào. Artifact là kho khác: đọc sau transaction vẫn ổn nếu bytes còn nguyên; mất bytes thì evidence incomplete.

## 1. Source capture API and exact envelope

```python
RuntimeStore.capture_failure_source(
    tenant_id, task_id, *, max_rows=10_000, max_events=10_000,
    max_source_bytes=16_777_216, page_size=500,
) -> dict
```

Arguments are strict nonboolean integers; ranges: rows/events 1..10_000, source bytes 1_024..16_777_216, page size 1..1_000. Identity inputs reuse `contracts.identity`. Limits may be lowered, never raised above these maxima. The row limit covers the aggregate captured table rows, including task, excluding authority/event rows. The event limit is separate. Exact top-level keys:

```text
schema=1, evidence_kind="runtime_failure_source", tenant_id, task_id,
snapshot, receipts, submissions, events, capture
```

`snapshot` has the existing `_snapshot` fields: task, budget, frontier, recovery_frontier, quarantined, nodes, attempts, dispatches, sandboxes, candidates, checkpoints, verifications, reviews. `receipts` and `submissions` are full task-scoped data arrays omitted by existing snapshot; no claims/outbox needed. `events` is ascending sequence. All table arrays are deterministically sorted by their logical identity (canonical bytes as a deterministic tie-breaker); ambiguity/duplicate identities are invalid, never deduplicated by silently discarding different records.

`capture` exact keys: method=`runtime_store_repeatable_read_v1`, schema_version=2, service_incarnation, frontier (integer), retained_from, history_start=1, history_end=frontier, status=`complete|incomplete`, reasons (sorted unique stable codes), limits (the four supplied bound arguments), table_counts (one count per captured table), event_count, source_bytes. `source_bytes` is length of canonical `{snapshot,receipts,submissions,events}`, excluding metadata to avoid self-reference. The entire returned canonical envelope must additionally fit max_source_bytes. No wall-clock capture timestamp: unchanged state gives deterministic bytes. Never expose authority cursor_secret or signed cursors.

Within `_read`, preflight authority/task encoded size before decoding them. Then count and bound encoded JSON bytes for all scoped captured tables and events through the pinned frontier before fetching JSON collections. SQLite may use `length(CAST(data AS BLOB))`; PostgreSQL `octet_length(CAST(data AS TEXT))`. Bound aggregate DB encoded bytes, and separately bound final canonical envelope because encodings/duplication differ. Fetch events in bounded sequence pages on that connection; use `<= frontier`. A same-transaction preflight followed by existing `_snapshot` is permitted if every table it reads was included and bounded. No artifact I/O, writer transaction, or mutator is allowed inside capture.

Limit overflow raises `ValueError` with stable prefix `capture_limit_exceeded:` and returns no truncated snapshot. Unsupported schema uses existing `Unsupported`; missing task uses existing `NotFound`. DB/transport failures propagate and must not become a successful empty capture. Full retained task history is required: retained_from=1, sequence exactly 1..frontier, nonempty task history. Retention gaps, missing sequences, mixed/old service incarnations produce `capture.status=incomplete` with reasons `retention_gap`, `event_sequence_gap`, `mixed_incarnation` as applicable. Malformed/cross-scope rows are rejected with `ValueError("invalid_source:...")`. Do not relabel pre-restore records with current incarnation. The extractor independently validates the envelope; capture metadata is not trusted merely because present.

**VI:** Giới hạn phải được kiểm trước khi lấy cả bảng vào Python; kiểm sau không còn là bounded capture. Nếu thiếu một dispatch mà vẫn cộng tiền, kết quả có thể giả thành zero. Vì vậy overflow không trả bản snapshot cắt ngắn.

## 2. Immutable record convention and extraction API

Each new record class (`FailureEvidence`, `RegressionCase`, `RegressionReview`) follows the existing frozen-manifest pattern: `payload: bytes`, `digest: str`, `read()` returns a detached JSON copy, `verify()` recomputes SHA256 and validates the closed versioned schema. Constructors/factories must reject noncanonical bytes or invalid schema; direct dataclass construction never bypasses downstream `verify()`. Reuse `service.artifacts.canonical_bytes/digest_bytes/digest_json`, not another JSON encoding. FrozenManifest retains its own existing encoding; verify its digest using its own API.

```python
extract_failure_evidence(
    source, *, kind, subject_id, window, source_provenance, lineage,
    artifact_reader, assignment=None,
) -> FailureEvidence
```

`kind` is exactly `failed_verification|unknown_dispatch`. `subject_id` is respectively verification_id or dispatch_id. Exactly one observation is returned; selection is explicit. `window` exact keys `start_sequence,end_sequence`; strict integers 1 <= start <= end <= source frontier. It filters the selected subject's relevant event only, never accounting or source history. `artifact_reader` is an injected trusted callable `(tenant_id, task_id, digest) -> bytes`, typically LocalArtifacts.get. It receives validated scope/digest, never a path from mined content.

`source_provenance` exact fields: `source_id` (identity label), `origin="trusted_local_runtime_store"`, `source_hashes` (1..64 relative path/label to SHA256 mappings; each name nonempty <=256, no absolute or traversal paths), `transformations=[]`, `redactions=[]`. This is explicitly a caller declaration; the adapter neither reads arbitrary source paths nor authenticates the caller. Transformed/redacted captures are unsupported because redaction can break joins. A later schema can bind original and transformed artifacts. Record `trust="local_caller_asserted_not_authenticated"` unconditionally, including imported captures. Never mark a digest as signature/authentication.

`lineage` exact fields: `family_id`, `source_case_id` (nonempty identity labels), `parent_evidence_digests` (0..32 unique SHA256), `split="development"`, `held_out_eligible=false`. It is caller-declared provenance preserved exactly in descendants. This adapter supplies no relabeling API. Recognized synthetic workload lineage must retain `synthetic-issue-tracker-v1`; do not silently map arbitrary repo IDs to the existing registry. The caller must not fabricate a registry relationship; source_case_id remains an explicit declared label. No change to the 42-task registry/population is authorized.

`assignment=None` produces null assignment and reason `unassigned_local_run`. Optional assignment exact fields: `manifest` (actual FrozenManifest), `row_id`, `runtime_submission_id`. Call `.verify()`, require development split, select one planned row, match row/task base_commit to runtime base_revision, grader_digest to runtime grader, and task repository to runtime repo_id; preserve manifest task_id separately from random runtime task_id. Derive runtime submission identity from `digest_json([tenant_id, submission.key])` and require it exists for the capture task. Store manifest_digest, full planned row, runtime_submission_id, and binding_kind=`caller_declared_runtime_mapping`. A runtime submission's request_digest hashes the original un-defaulted request, so **do not compare it to frozen contract_digest**. This metadata never creates an analyzer row or modifies assigned denominators. Ambiguous/mismatched mapping raises ValueError.

Input metadata schema errors, unsupported kind, malformed non-JSON/nonfinite values, oversized supplied source or impossible window raise ValueError. Source semantic defects yield a frozen record with `status=invalid|incomplete`; no regression may be proposed from such a record. Do not catch programmer/DB exceptions as missing evidence. Incomplete means absent or unsupported evidence; invalid means contradictory/malformed evidence. Invalid wins over incomplete. A structurally sound capture with a selected pass/error verification, resolved dispatch, missing subject or out-of-window selected event yields incomplete with `subject_not_supported_failure`, `subject_missing`, or `subject_outside_window`, never a fabricated failure.

**VI:** Mapping sang planned row là khai báo có kiểm identity, chưa phải kết quả thí nghiệm. Cùng task name không đủ để nối hai run. Generic runtime units cũng chưa phải USD. Adapter này không được tự xuất accepted=1.

### FailureEvidence payload

Exact top-level fields:

```text
schema=1, evidence_kind="runtime_failure_observation", kind, status, reasons,
source_digest, snapshot_digest, events_digest, source_provenance, trust,
scope, window, subject, identities, artifacts, accounting, lineage, assignment,
unavailable, regression_eligible
```

`reasons` is a sorted unique list of stable codes. `source_digest=digest_json(source)` and snapshot/events digests use their exact saved objects. `scope` exact fields: service_incarnation, tenant_id, task_id, current_generation, frontier, retained_from. `subject` exact fields: id, event_id (nullable), sequence (nullable), generation (nullable), attempt_id (nullable), node_id (nullable), dispatch_id (nullable), verification_id (nullable), effect_state (nullable), billing_state (nullable), outcome (nullable). `identities` exact fields: contract_digest, base_revision, candidate_id (nullable), tree_digest (nullable), grader_digest, environment_digest, input_digest (nullable). Nulls need an entry in `unavailable` mapping field paths to fixed reason strings (e.g. `not_applicable`, `not_recorded_by_runtime`, `unassigned_local_run`, `missing_source`). No invented run ID: tenant/task/incarnation scope is the run identity.

`artifacts` is sorted unique inventory of `{tenant_id,task_id,digest,size,status}` for all recognizable scoped artifact refs anywhere in source; status `verified|missing|invalid`. Recompute SHA256 and length from returned bytes, check scope before read, and deduplicate by digest within this one task. Reject inconsistent sizes for identical digest. Fixed caps: 256 unique refs, 8MiB per artifact, 32MiB aggregate returned bytes; check declared sizes/counts before reading. The trusted reader must itself enforce bounded reads (LocalArtifacts does); reject a returned oversized value. Missing FileNotFoundError/KeyError becomes `artifact_missing` incomplete; malformed ref, wrong scope, hash/size mismatch or malformed required verification JSON becomes invalid. Other reader/transport exceptions propagate. Never write, execute, import or interpret instructions inside an artifact. Nonverification artifacts remain opaque bytes and their content is not copied into the observation. Reference closure here means recognizable refs present in captured JSON, not recursive discovery inside opaque artifact contents.

`regression_eligible` is true only for complete supported observations with all required joins/artifacts/accounting validated. It means eligible to create a pending development proposal, not executable acceptance.

### Required structural and causal joins

Validate schema, all root/task/scope/frontier agreement, strict sequence/counts/integers and finite times, complete sequence coverage, event uniqueness, and event tenant/task/incarnation. Validate task contract_digest against exact contract, recompute captured budget, and uniqueness of every attempt, dispatch, candidate, verification and receipt identity. A duplicate event/row is invalid; idempotent runtime retries ordinarily create no duplicate row. Never sum receipt events as costs. Check nested owners/references against scope. No unrelated tenant data is accepted. Older current_generation is not a join requirement: a failed task increments task.generation while preserving causal verification/owner generation.

Failed verification: require an immutable verification row with outcome=`fail`; exactly matching `verification.recorded` payload and ID; recompute verification_id from row excluding verification_id/recorded_at. Join its candidate_id/generation/contract_digest to exact candidate and frozen task contract. Validate candidate tree and base_files using service `sha256-text-tree-v1` hashing, not workload registry's different tree hash. Compare grader/environment to contract, tree to candidate. Require candidate is recorded in its causal history (`candidate.accepted` for worker or `head.integrated` for integration) before verification. Generation derives from candidate/verification, not the now-revoked task. Do not require candidate still be current head. Verification evidence_ref must be a standard scoped artifact ref containing JSON with strict `passed=false` and matching tree_digest/grader_digest/environment_digest. Preserve extra verifier fields only through its artifact identity; unknown/unsupported verifier format is incomplete (`unsupported_verification_artifact`). CPU numerical observation kind is explicitly unsupported even if it carries a `passed`/`outcome` field. No trust is gained by copying these identity fields into CPU data.

Unknown dispatch: select only snapshot effect_state=`unknown`; require exact matching `dispatch.intent.parameters`, owning attempt/owner, and at least one matching terminal receipt event and receipt row. Reconstruct latest dispatch receipt knowledge in sequence order, allowing effect/billing to advance independently and result_ref to remain bound across later null refs. Latest receipt_id, result_ref, actual_units, billing_state and effect_state must agree with snapshot. `dispatch.bound_violation` also carries a receipt and participates. The selected event is the latest terminal receipt at the cut and must fall inside window. The generation is owner.generation. Never classify mere `in_flight` as observed Unknown. Missing result_ref is legal for Unknown and is recorded unavailable. `input_digest` is an intent identity, not proof that matching request bytes are present.

Recommended stable semantic codes: `invalid_scope`, `invalid_identity`, `invalid_event`, `duplicate_identity`, `event_sequence_gap`, `retention_gap`, `mixed_incarnation`, `missing_causal_record`, `source_disagreement`, `artifact_missing`, `artifact_integrity`, `artifact_limit_exceeded`, `unsupported_verification_artifact`, `accounting_mismatch`, plus selection codes above. Closed-schema metadata errors throw; record reasons never embed raw exception text, paths, keys or provider secrets.

**VI:** Fail receipt ở generation1 vẫn đúng dù fail_execution đổi task sang generation2. Nhưng đổi candidate/grader/env là contradiction. Với Unknown, bill có thể settled9 và effect vẫn unknown: không được suy ra “charge known” nghĩa là “tool succeeded”.

### Accounting and exact tiny trace

`accounting` exact fields: `scope="whole_task_at_frontier"`, `unit="runtime_budget_units"`, `rate_snapshot` (exact contract value, nullable), `rate_snapshot_digest` (nullable), `spent_units`, `reserved_units`, `attempt_allowance_units`, `unsettled_bound_units`, `unknown_effect_count`, `dispatches`, `attempts`, `input_tokens=null`, `output_tokens=null`, `infrastructure_cost=null`. Token/infrastructure absence is explicit `not_recorded_by_runtime`, never zero. No conversion to USD; even provider-shaped rates do not upgrade generic runtime accounting units.

Each dispatch entry: dispatch_id, attempt_id, node_id (from owner), generation, kind, effect_state, billing_state, bound_units, actual_units (nullable), receipt_id (nullable). Each attempt entry: attempt_id, node_id, generation, allowance_remaining. Include all generations/roles/retries regardless of selection window. Runtime has no authoritative parent/child role field: preserve node IDs; do not invent roles or distributed-agent semantics. Validate strict nonnegative counts and known state combinations. Derive

```text
spent_units = sum(actual_units for each unique settled dispatch)
attempt_allowance_units = sum(allowance_remaining for each unique attempt)
unsettled_bound_units = sum(bound_units for each unique nonsettled dispatch)
reserved_units = attempt_allowance_units + unsettled_bound_units
```

Require equality with snapshot.budget.spent/reserved/limit and contract limit identity. Historical bound violation is allowed and retained; do not reject truthful spent > bound/limit as an accounting arithmetic error. Example: allowance40, dispatch bound12 → allowance28+bound12=reserved40. Receipt Unknown actual=None retains40. Retirement clears28 leaving12. Late actual9 leaves spent9/reserved0 while effect may remain Unknown. Three settled dispatches under declared node labels parent10/child7/summary3 produce20 once, even when only summary's receipt is selected. These are predicted control values, not measured results.

**VI:** Cost thuộc cả task, không thuộc đoạn trace đang nhìn. Nếu chỉ chọn event summary3 rồi báo total3, adapter đã làm biến mất17. Receipt lặp không thêm cost vì nguồn cộng là dispatch ledger duy nhất.

## 3. Regression fixture, predicate and proposal API

```python
evaluate_regression_fixture(predicate_id, fixture, *, evidence) -> bool
freeze_regression_case(
    evidence, *, fixture_ref, predicate_id, source_hashes,
    artifact_reader, fix_revision=None,
) -> RegressionCase
record_regression_review(
    case, *, reviewer_id, reviewer_kind, disposition, reasons, reviewed_at,
) -> RegressionReview
```

All downstream functions call evidence/case `.verify()`. `evidence.status` must be complete and regression_eligible true. No caller-supplied callable, module/import name, expression, regex, grader source or executable precondition is allowed. The fixed registry has exactly:

| Predicate ID | Evidence kind / constant precondition | Fixture expected value, derived from evidence |
|---|---|---|
| `verification.exact_binding.v1` | failed_verification / `complete_failed_verification` | exact contract_digest, base_revision, candidate_id, tree_digest, grader_digest, environment_digest, verification_id, generation, outcome=`fail` |
| `dispatch.unknown_accounting.v1` | unknown_dispatch / `complete_unknown_dispatch` | selected dispatch_id, generation, effect_state=`unknown`, billing_state, bound_units, actual_units, plus whole-task spent_units/reserved_units/attempt_allowance_units/unsettled_bound_units |

Predicate input `fixture` is a JSON object with **exactly** the selected expected-value keys above. Values receive strict type/schema validation; a well-formed but wrong identity/state/amount returns false. Malformed values or unknown/mismatched predicate raise ValueError. Expected values come from verified evidence, never from expected fields supplied in the fixture. This is deliberately a data-invariant regression. A matched failed-verification fixture returns true because attribution is correct; it does not turn fail into pass.

`fixture_ref` is a same-tenant/task standard artifact ref, verified through the reader with a 64KiB ceiling. Its JSON exact fields are `schema=1`, `evidence_digest`, `predicate_id`, `known_good`, `known_bad`. known_good/known_bad are fixtures of the specified predicate schema. Require matching evidence/predicate IDs, distinct control digests, evaluate good=true and bad=false. Reject reversed/unchanged controls and any plausible-wrong “good” identity/amount. No fixture construction/execution is hidden in this API. A fixture author creates bounded JSON and stores it with existing LocalArtifacts.put_json; tests/demo use this normal API.

Case exact payload: schema=1, evidence_kind=`development_regression_case`, evidence_digest, fixture_ref, fixture_digest (actual bytes), predicate_id, precondition (constant above), invariant (fixed human-readable registry description), known_good_digest, known_bad_digest, control_results={known_good:true,known_bad:false}, source_hashes (same validation as provenance), fix_revision (null or nonempty <=128 string declared revision), lineage (exact evidence lineage), review_state=`pending`, trust=`local_caller_asserted_not_authenticated`. Do not interpret a provided fix_revision as proof of a successful code fix. Source hashes remain caller-declared, frozen and reviewable.

Review exact payload: schema=1, evidence_kind=`development_regression_review`, case_digest, reviewer_id (identity), reviewer_kind=`human|ai`, disposition=`approved|rejected`, reasons (1..16 nonempty strings <=2048 each), reviewed_at (finite nonboolean nonnegative timestamp), authority=`caller_declared_review_only`. Case remains immutable and pending; review is a separate immutable record, not a rewrite. No latest-review selection, automatic promotion, authorization or production review action in this slice. Identical review arguments converge to identical digest; changed review arguments produce a new record. AI review is always labeled ai in delivered examples.

**VI:** Good control chứng minh adapter giữ identity/tiền đúng; bad control phải thật sự bị predicate đánh false. Case giữ pending vĩnh viễn như bản proposal gốc. Review là object riêng trỏ về đúng case digest, để người đọc biết ai đã khai báo review gì mà không sửa lịch sử.

## 4. Failure behavior, experiments and delivery gates

| Distinguishing experiment | Required observable result |
|---|---|
| Real local failed verification over frozen incorrect fixture, then fail_execution | Complete observation preserves original candidate/verification generation despite current task generation increment |
| Concurrent committed write between capture queries | All reads stay at one pinned frontier; later write appears only in a subsequent capture |
| Same cut captured twice; mutate read() output or original input afterwards | Equal canonical identity, record payload unchanged |
| Delete event middle/prefix; duplicate sequence; change scope/incarnation | Incomplete gap/mixed history or invalid duplicate/scope; no eligible regression |
| Lower row/event/source-byte limits; large DB row | Reject before unbounded collection decoding; no truncated cost record |
| Change candidate tree, verifier grader/env, receipt/contract ID or cross-tenant ref | Invalid evidence; never reuse verdict for changed candidate |
| Delete an artifact referenced only by earlier event/checkpoint; corrupt bytes or length | Missing→incomplete; mismatch→invalid; artifact cap enforced |
| Unknown with unsettled12 after retirement; Unknown with settled9 | Separate effect/billing retained; exposure12 or spent9 respectively |
| Three node-labelled settled costs10+7+3, narrow window, repeated idempotent receipt | Total20, unique dispatch counts, no invented agent roles |
| Valid good/bad fixtures; unchanged or plausible-wrong good fixture; unknown predicate or executable text | Only actual good=true/bad=false pair creates pending case; unsupported formats rejected |
| Rename evidence/case and ask held_out, mutate lineage, attach CPU pass | Rejected/no promotion/no numerical acceptance route |
| Optional verified development manifest mapping vs changed base/grader/repository/submission | Metadata binds exact row or rejects; analyzer assigned denominator untouched |
| AI review and duplicate review | Separate ai-labelled immutable review; no production store mutation |
| Snapshot/events/receipt append counts before and after adapter | No change; no execution/payment/network call from adapter |

Tests use disposable local stores and trusted frozen fixtures. No paid provider, candidate replay, GPU or new dependency is required. SQLite must be exercised; PostgreSQL same-transaction behavior should be covered under existing opt-in backend facility when locally available, otherwise explicitly pending. Source-bound validation records should record selected/full relevant test commands, actual results/skips, Ruff, and SHA256 of changed production/tests/spec files. No repeated unchanged-code testing just for documentation edits.

Implementation lanes after root freeze: (A) storage capture + evidence only; (B) regressions only, consuming this exact evidence schema; (C) tests + bounded local demonstration + evidence record. Independent reviewer owns no implementation lane and inspects final source/spec/test differences; repairs are reviewed before completion. Root owns integration, freeze declaration, context/coverage updates and final delivery claims. Preserve all existing source/runs; write new demonstration output under a new run directory. This spec creates no learning evidence; H0 and H0–H15 human mastery remain pending.

**VI:** Acceptance ở đây là engineering gate của adapter: đọc nhất quán, giữ nguyên identity và cost, kiểm control sai đúng, không sửa authority. Nó không phải “Huy đã master”, “model sửa code tốt”, hay “GPU nhanh”.

## Resolved boundaries and deferred work

This is an API/library slice; no general filesystem importer, discovery CLI, arbitrary historical replay, outcome exporter, authenticity service, authenticated review service, USD conversion, role inference, cross-task aggregation or old-incarnation reconstruction. Restored histories, transformed/redacted sources and unsupported verifier payloads are honestly incomplete. A local caller with write access to DB/artifacts can forge mutually consistent data; these APIs cannot solve that trust boundary. Frozen controls evaluate projection invariants and do not provide fresh candidate correctness. These limitations are intentional and must survive documentation and examples.

**VI:** Giới hạn nhỏ giúp tránh “đủ field là trusted”. Muốn nhận nguồn ngoài hoặc đo repair thật sau này phải thêm contract riêng; không kéo chúng vào bằng một boolean pass hay tên file mới.

## Review addendum A — unavailable accounting is not zero

**2026-10-10, frozen before the accounting repair.** Independent review reproduced a malformed/missing attempt-owner join causing the projection to discard accounting rows and emit zero totals despite a nonzero captured budget. The observation was invalid, but `whole_task_at_frontier` zero still overstated what was known. Preserve the source identity and any structurally valid ledger rows without reporting partial sums as full-task totals.

The five derived accounting fields (`spent_units`, `reserved_units`, `attempt_allowance_units`, `unsettled_bound_units`, `unknown_effect_count`) are nullable when a missing, malformed or causally inconsistent accounting ledger prevents whole-task derivation. Set all five to null together, add `accounting_unavailable`, and record `unavailable["accounting.<field>"]="missing_source"`. Such observations must be incomplete or invalid and regression_eligible=false. Complete observations retain strict nonnegative integer totals and all original equalities. The three already-null usage/infrastructure fields retain their existing meaning. A contradictory snapshot total with a fully validated ledger may retain the independently derived integer totals while marking the observation invalid; it must not silently rewrite the snapshot.

`FailureEvidence.verify()` must distinguish fully derived accounting from explicitly unavailable accounting, validate any retained row structure, and reject partial-null totals or an eligible record with unavailable accounting. This adds no accounting authority, outcome exporter or new predicate. Regression factories continue to accept only complete observations. Distinguishing test: corrupt an owning attempt in a source with settled9 or unresolved12; the resulting invalid observation retains the source digest and reports unavailable totals, never measured0.

**VI:** “Record invalid” chưa đủ nếu bên trong vẫn ghi total=0. Khi không nối được ledger đầy đủ, ta biết phép cộng chưa đáng tin; null nói đúng điều đó. Zero chỉ được dùng khi toàn bộ nguồn hợp lệ thật sự cộng ra zero.

## Review addendum B — preserve aggregate overspend exactly

**2026-10-10, frozen before the aggregate validation adjustment.** Individual runtime dispatch/allowance fields retain their existing strict signed-64-bit nonnegative bounds. Derived whole-task sums are exact nonboolean nonnegative integers and are not constrained to the per-row maximum. Several already-dispatched operations can settle after a bound violation quarantines new execution; their truthful combined consumption can exceed that maximum. Existing captured row/byte caps bound this arithmetic. Apply the same rule to the four aggregate unit fields in Unknown regression fixtures. Counts and individual dispatch amounts retain their original bounds. Distinguishing test: two legitimate retained large settlements sum exactly above the per-row maximum; extraction and predicate controls preserve that amount without overflow, truncation or refund.

**VI:** Giới hạn của một receipt không phải giới hạn của tổng nhiều receipt. Quarantine dừng việc chạy mới nhưng không xóa bill của việc đã dispatch; tổng vượt budget vẫn phải được giữ đúng.
