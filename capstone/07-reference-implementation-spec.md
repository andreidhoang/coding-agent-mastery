# Reference implementation contract

Architecture contract: **2026-10-08**; production verification: **2026-10-09**; course integration design: **2026-10-10**. Architecture author: AI (Astra role). This document records the implementation sequence explicitly requested by Huy: build the reference codebase first, then learn its mechanisms from exact code/data/tensor traces. That request supersedes the earlier learn-before-build ordering for this delivery. Human prediction, teach-back, transfer and mastery remain separate and unearned by generated code.

**VI:** Code là đối tượng để học và kiểm chứng, không phải chứng chỉ mastery. Thay thứ tự build không làm giảm yêu cầu chứng minh invariant hoặc cho phép gọi một demo là production.

## Scope and evidence contract

Deliver one source tree under `service/`, with runnable local end-to-end behavior and real deployment-target adapters. The reference default uses SQLite and trusted disposable fixtures; the deployment path includes PostgreSQL, FastAPI, Temporal and a constrained Linux container supervisor. These are two configurations of the same domain contracts, not two unrelated harnesses. Preserve `lab/`, vendored `references/`, prior runs and original design documents.

A source surface is **implemented** only when its body performs the promised behavior; an interface that raises an unsupported error is **fail-closed scaffolding**. Import/compile success is **static validation**; a real dependency integration test is **local integration evidence**; a measured failure/load/restore exercise is **operational evidence**. None alone establishes live-model coding quality, hostile multi-tenant safety, held-out scaling gains or hiring readiness. Final delivery must enumerate which category each adapter actually reaches.

**VI:** Có đủ file không có nghĩa đủ implementation. Postgres chạy thật mới kiểm được dialect và transaction; container chạy thật mới kiểm được một phần boundary; cả hai vẫn chưa chứng minh service chịu workload và attacker đã khai báo.

**Reading rule after implementation:** This chapter preserves the target engineering contract. The module/API inventory below has been checked against the delivered source; other normative requirements remain targets unless the [implementation coverage register](08-implementation-coverage.md) supplies their current status and evidence. Source gaps and unmeasured operations are different categories.

The [2026-10-11 readiness plan](../research/system-readiness-plan-2026-10-11.md) and [verification record](../research/system-readiness-verification-2026-10-11.json) track current bounded delivery and qualification gaps. The [2026-10-09 production code review](../research/production-code-review-2026-10-09.md) and [its verification record](../research/production-review-verification-2026-10-09.json) retain their dated repairs and outcomes; earlier source identities do not validate every later edit.

**VI:** Đọc “MUST” hay bảng acceptance như yêu cầu cần đạt, không như kết quả đã đo. Dùng chapter 08 để biết code nào có thật, behavior nào còn thiếu và experiment nào chưa chạy.

## Architectural decisions

**Audit repair gate, 2026-10-10:** the [bounded refactor specification](../research/codebase-refactor-spec-2026-10-10.md) freezes reproduced identity, protocol, physical-retirement and evaluation corrections before implementation. Repair these existing boundaries before adding the shared failure-evidence adapter or NV-S1 execution. It preserves schema 2, existing owners, NVIDIA slice order and hackathon priority; [coverage](08-implementation-coverage.md) records actual delivery rather than this design authorization.

1. Python control plane with SQLAlchemy Core 2.x schema/transactions, SQLite `BEGIN IMMEDIATE`, and PostgreSQL through psycopg. Each mutating PostgreSQL transaction first locks one service-authority row `FOR UPDATE`. This deliberately coarse serialization is a tractable bounded reference; throughput must be measured before finer locks replace it. All correctness checks and state/event/outbox changes are in that transaction. No provider calls, subprocesses or artifact uploads occur while it is held.
2. Authority belongs to `RuntimeStore`; immutable bytes belong to a tenant-scoped content-addressed artifact store. Workers propose results through trusted application code. A digest identifies bytes; tenant/task membership authorizes access.
3. A persistent outbox bridges domain state and a local dispatcher or Temporal workflow. Deliveries are at least once and keyed by stable command identity. Activities consult domain receipts; workflow replay cannot repeat an uncertain effect. Workflow/SDK history compatibility needs separate tests.
4. Provider adapters retain complete response entity bytes before semantic parsing, separately validate usage and preserve provider-supported continuation artifacts. A malformed tool/terminal envelope cannot erase trustworthy billing evidence or authorize tools; missing/untrusted usage retains liability. Text, partial JSON and exponent-overflow numbers fail closed. Live credentials remain outside execution containers.
5. Execution has explicit trusted-local and Linux-container modes. Trusted-local accepts only repository-owned fixtures. Container mode requires a digest-pinned image, no network by default, non-root identity, no control sockets/secrets, narrow mounts, resource caps and supervisor-owned receipt creation. Instance nonce plus immutable container ID binds cleanup; a name alone grants no retirement authority. The external verifier snapshots candidate input and latches transport/boundary failures independently of expected candidate exceptions. Unavailable enforcement rejects execution; it never falls back silently.
6. CPU attention/KV/cache and offline trajectory-objective references are runnable. A CUDA attention benchmark has hardware preflight; an Anthropic transport/harness requires explicitly approved model/rate bounds. Distributed training and a deployed GPU serving engine are not implemented. Cache/allocation simulations are labeled as simulations, never measured GPU behavior.

**VI:** Chọn coarse lock làm mọi writer xếp hàng giúp invariant dễ kiểm tra. Cái giá là throughput; đó là tradeoff đo được. Không được đổi thành nhiều lock chỉ vì “production hay làm thế” trước khi biết bottleneck và thứ tự lock mới.

## Module ownership and public seams

The following inventory describes **current source**, not the broader proposed module map in earlier chapters.

| Module | Current state/data owner and public responsibility |
|---|---|
| `service/contracts.py` | JSON validation/copying, domain exceptions, task contract defaults and seven-field ownership dictionaries; no enum-class layer |
| `service/storage.py` | Shared SQLAlchemy schema; serialized authority, task/node/attempt/dispatch/budget/environment/event/outbox/integration/review transitions |
| `service/migrations/` | Explicit offline schema-1→2 identity rewrite and writer compatibility protocol; not an automatic startup or rolling migration |
| `service/artifacts.py` | Canonical encoding/hashing, local immutable bytes and explicit S3 adapter; accepted task-reference authorization additionally belongs to storage/API |
| `service/protocol.py` | Strict bounded JSON, SSE/tool-stream parsing, `ToolCall` schemas and call/result linkage |
| `service/providers.py` | Scripted provider and explicit Anthropic and Nebius transports/response parsing; preserve provider-specific continuation. Nebius source observed October 10; the dated October 9 verification does not validate later additions |
| `service/billing.py` | Frozen integer provider envelope, conservative reservation bound and usage charging |
| `service/context.py`, `service/context_retrieval.py` | Legacy full-history projection plus opt-in deterministic old tool-body offloading and current-projection scoped byte retrieval; unsupported/irreducible overflow fails closed |
| `service/harness.py` | Capability tool broker and scripted/live-provider loop, journaled dispatches, checkpoints and explicit restored-state consumption |
| `service/execution.py` | Guarded workspace edits/snapshots, bounded launcher and constrained Docker supervisor; uncertain provisioning/retirement remains explicit |
| `service/integration.py` | Exact text-tree/base manifests and deterministic conflict-detecting integration |
| `service/verification.py` | Frozen-control verifier and Linux candidate RPC with expected checks in the external trusted grader |
| `service/recovery.py` | Recovery plan and exact checkpoint reconstruction with dispatch-frontier checks; grants no execution authority |
| `service/engine.py` | Fixture-specific coordinator with frozen per-file graph, patch concurrency, completed-branch/head reuse, admitted verifier and review eligibility |
| `service/api.py` | FastAPI bearer/repository authorization, bounded ingress, task/status/snapshot/event/cancel/artifact/review routes |
| `service/workflows.py` | Local dispatcher, Temporal relay/workflow and injected task activities; consumes domain notifications without replaying their effects |
| `service/reporting.py` | Compact evidence report and local JSON/HTML outputs |
| `service/cli.py` | Exactly `doctor`, `workloads`, and `demo`; demo accepts output/database/image/worker/workload settings and writes evidence reports |
| `evals/` and `compute/` | Separate module entry points for frozen-outcome analysis/synthetic demo and CPU tensor/cache/objective trace with CUDA preflight; fault/replay checks live in tests and Python APIs |

The signatures below match current public `RuntimeStore` methods. Results are JSON-safe dictionaries/lists unless noted; ownership is a validated dictionary. These are trusted in-process seams, not all public HTTP endpoints. HTTP currently uses `/tasks` (without a `/v1` prefix), plus `/health`; the earlier `/v1` endpoint table is the proposed product contract.

```python
RuntimeStore(url, artifact_store=None, *, service_slot_limit=16,
             tenant_slot_limit=8, service_budget_units=10**9,
             tenant_budget_units=10**8)
close() -> None
submit(tenant_id, key, contract) -> dict
get_task(tenant_id, task_id) -> dict
set_graph(tenant_id, task_id, generation, nodes) -> dict
claim(tenant_id, task_id, node_id, claim_id, reserve_units, lease_seconds) -> dict
heartbeat(owner, lease_seconds) -> dict
begin_dispatch(owner, action_id, dispatch_id, kind, input_digest, bound_units) -> dict
finish_dispatch(tenant_id, dispatch_id, receipt_id, effect_state,
                actual_units=None, result_ref=None) -> dict
accept_candidate(owner, manifest) -> dict
cancel(tenant_id, task_id, request_id) -> dict
retire_sandbox(tenant_id, sandbox_id, evidence_ref) -> dict
checkpoint(owner, manifest) -> dict
snapshot(tenant_id, task_id) -> dict
events(tenant_id, task_id, cursor=None, limit=100) -> dict
integrate(tenant_id, task_id, generation, candidate_ids,
          expected_revision, manifest) -> dict
record_verification(tenant_id, task_id, generation, candidate_id,
                    tree_digest, grader_digest, environment_digest,
                    outcome, evidence_ref) -> dict
publish_review(tenant_id, task_id, generation, candidate_id,
               verification_id, expected_revision) -> dict
record_review(tenant_id, task_id, review_id, reviewer, decision, key) -> dict
list_outbox(limit=100, kinds=None) -> list
ack_outbox(command_id) -> None
quarantine_restore(new_incarnation, recovery_frontier) -> None
resume_after_reconciliation(evidence_ref) -> None
set_admission(accept_new_tasks: bool) -> dict
authorize_artifact(tenant_id, task_id, artifact_digest) -> dict
service_state() -> dict
reserve_environment(tenant_id, task_id, generation, kind, reservation_id) -> dict
fail_execution(tenant_id, task_id, generation, reason, evidence_ref) -> dict
```

`integrate`, `record_verification`, `publish_review`, settlement and restore are trusted control-plane entry points, never model tools. Method naming is not an access-control mechanism: API routes must not expose worker-supplied verifier or operator authority. Exceptions: `Conflict`, `Fenced`, `BudgetExceeded`, `CapacityExceeded`, `NotFound`, `Unsupported`, `ResetRequired`. Reads scope tenant before lookup; a caller cannot infer other tenants' records.

**VI:** Worker gọi hàm có tên “verify” không làm nó thành verifier. Boundary thật là nơi credentials, receipt creation và route authorization được giữ khỏi process chạy candidate.

## Frozen records and transition rules

The contract minimally contains `repo_id`, `base_revision`, `requirements`, `capabilities`, `execution_deadline`, `review_deadline`, `profile`, `patch_slot_limit`, `budget_units`, `max_nodes`, `max_attempts`, `model`, `grader_digest`, and `environment_digest`. Defaults must be serialized into the frozen contract. Reject unknown or ambiguous fields where they affect authority; reject duplicate JSON keys, nonfinite numbers, negative limits and booleans masquerading as integers. Monetary units are checked nonnegative integers, with a named rate snapshot when live billing is enabled.

The seven-part ownership tuple is `(service_incarnation, tenant_id, task_id, generation, node_id, node_epoch, attempt_id)`. A claim returns this tuple plus a concrete sandbox ID, lease and reservation identity. Claim identity binds its full parameters: duplicate valid claim returns the same grant, changed body conflicts, revoked claim never silently obtains a new epoch. A sibling's epoch does not invalidate another node. Worker admission/candidate/checkpoint writes recheck the applicable owner, lease, dependencies, service flag, task state and database deadline atomically. Trusted integration/verifier/publication methods use the current store incarnation, task generation, accepted frontier and head revision; there is no separate leased integrator epoch in this implementation. A `RuntimeStore` caches its execution incarnation, so restore requires a freshly constructed controller before execution can resume. Final eligibility records the database decision time; a separate authoritative commit-confirmation timestamp is not currently persisted by the store.

**VI:** Owner token giống vé gắn đúng chuyến, toa và lần vận hành. Nó không có giá trị vĩnh viễn chỉ vì chữ ký hay ID đúng; database phải xác nhận chuyến hiện tại chưa bị hủy và lease chưa hết.

Each claim atomically reserves physical capacity and shared allowance. For every applicable account, `spent + reserved <= limit`. Service/tenant/task counters are overlapping constraints over the same liability, not three charges. Dispatch reservation consumes its attempt allowance by transfer, not double reservation. Settlement must reject actual usage above an enforceable bound as a violation requiring containment; it must never hide overage by truncation. Duplicate receipt identity with the same body is idempotent; changed body conflicts. Unknown billable effects retain exposure after cancellation and lease expiry.

Known result artifacts remain immutable across later billing settlement. A duplicate tool dispatch without its durable known result is rejected before any effect, even if its effect state is terminal. Accepted-candidate acknowledgement retries return the matching durable record instead of creating a second candidate. Private dispatch/candidate identities use canonical `[tenant_id, logical_id]` hashes in schema 2. Schema-1 databases require the [explicit offline migration and writer protocol](../service/migrations/002_identity-and-writer-protocol.md), with all old writers stopped; startup is not a migration or a rolling-upgrade gate.

**VI:** ID `a:b` ghép bằng dấu `:` có thể trùng với cách tách tenant/ID khác, nên schema 2 hash một tuple canonical. Đổi key không sửa lịch sử đã mất; còn result và liability phải giữ nguyên qua migration và retry. Writer guard là compatibility check của SQL tin cậy, không phải security boundary cho tenant thù địch.

Execution state, physical sandbox state, review state and billing knowledge are distinct. Cancellation increments task generation, revokes new admission/acceptance and emits stop commands. It does not claim immediate process death or zero charge. Replacement waits for previous environment retirement and operation-specific reconciliation. `retire_sandbox` releases a slot once only with trusted observation. Unknown teardown retains capacity.

**VI:** Có thể task đã cancel nhưng sandbox vẫn sống và tiền vẫn chưa đối soát. Ba state này khác nhau về vật lý nên không gộp thành `done=True`.

## Artifacts, verification and replay

Store immutable bytes before accepting their references; verify SHA-256, size and namespace. Candidate manifests bind base, ordered patches, exact resulting tree, requirement/dependency versions, producer and environment. Text changes reject traversal, absolute paths, unsupported symlinks/submodules and grader edits. Integration reconstructs bytes externally, then atomically compares its expected head revision and eligible parent references. Any transformed tree needs a new candidate and verification.

Verification uses a fresh reconstructed tree and fixed trusted grader; candidate stdout cannot author a verdict. Receipt binds candidate/tree/grader/environment/contract and supervisor identity. Only a current exact passing receipt permits review eligibility. Human review follows its own deadline and cannot resume execution. Protected grader separation on the same trusted local host is a test of logical authority, not hostile-process isolation evidence.

Checkpoints retain contract, graph, accepted frontier, provider artifact references, workspace manifest, pending calls and unresolved dispatch/billing state. The delivered `restore_checkpoint` reconstructs workspace/protocol data and checks an authoritative dispatch-ID frontier; it grants no authority. The caller must separately acquire a current owner. Automatic active-attempt replacement is not supplied by this helper. An event cursor binds service incarnation, tenant, task and sequence; wrong incarnation yields reset-required, expired retained history yields explicit gap, and another tenant's cursor is rejected. Duplicate events remain identifiable by immutable event ID. A DB backup restore starts quarantined, uses a fresh incarnation, fences old control-plane actors and reconciles beyond-backup effects before execution can resume. A boolean `reconciled=true` is not sufficient evidence.

**VI:** Event replay trả lời hệ thống đã commit quyết định nào; nó không chứng minh request ngoài mạng chưa chạy. Cần đối chiếu receipt và effect ledger trước khi replay hành động có side effect.

## Tiny distinguishing trace

Proposed trace, not a measured result: task `T`, generation 1, budget 100 units; worker A claims epoch 1 and allowance 40. Dispatch D transfers 12 of that allowance into billable exposure. A edits a private file; process dies before its result is committed. Durable state proves intent, not result. Mark D unknown and retain its 12; retire the sandbox only after observing termination. The remaining safely unused allowance may be released. A replacement at epoch 2 cannot blindly repeat D; an operation-specific reconciler must prove the local effect reconstructible or choose a new safe environment/action. An epoch-1 candidate is rejected. After cancel, a delayed charge receipt of 9 settles once and releases 3, but cannot publish a candidate or revive the task.

**VI:** Nếu test chỉ kiểm “stale candidate bị reject” mà không kiểm 12 units còn giữ, hệ thống vẫn có thể overspend qua retry. Một trace đúng cần nhìn cả authority, bytes, slot và tiền.

## Requirement coverage and evidence gates

This is the **target delivery acceptance matrix**, not a current implementation checklist. For each requirement, consult the [current coverage register](08-implementation-coverage.md) and its linked test/run records for implemented, partial, blocked or unmeasured status. A target such as versioned replanning or load/rollback tooling in this table does not assert that the corresponding source exists. Passing local tests never automatically completes the original production requirement.

| Requirements | Required source delivery | Local distinguishing evidence | Deferred operational/research evidence |
|---|---|---|---|
| SYS-01 / RT-01 / OP-01 | Frozen task API, authorization, retained idempotence | Duplicate/changed payload and cross-tenant denial | Real identity/repository grants, retention contract |
| SYS-02 / RT-05 | Protocol adapter, bounded stream assembler, broker schemas | Truncated/duplicate/conflicting calls cause no extra effect | Pinned live-provider protocol/usage compatibility |
| SYS-03 | Linux container supervisor and trusted fixture mode | Denied mounts/network, timeout/output/process probes | Hostile-code threat review, disk/cgroup/kernel escape scope |
| SYS-04 / RT-02,04,11 | PostgreSQL/SQLite authority, intent ledger, outbox, Temporal adapter | Real DB races, crash receipts, stale owner/duplicate delivery | Distributed partitions, Temporal saved-history version replay |
| SYS-05 / RT-09 | Artifact checkpoint/context/restart protocol | Fresh-process restore retains constraints/unknowns | Multi-day live-model constraint retention |
| SYS-06 / RT-03 | Versioned DAG, 1/2/4 research profile, physical slots | Competing claims and retired/unknown environment accounting | Declared larger operating envelope/fairness |
| SYS-07 / RT-07,08 | Exact-tree integration, independent verifier, review gate | Wrong/deleted tests, stale tree, forged/late receipt fail | Protected grader under hostile code and human review |
| SYS-08 / RT-06 | Hierarchical integer budget/settlement | Simultaneous reservations and duplicate late receipt | Provider upper-bound/billing reconciliation validation |
| SYS-09 / RT-10,12 / OP-03 | Durable events, cancellation, fault harness | Rejection/cleanup/settlement timelines and saved trace | Cross-host time uncertainty and retention operations |
| SYS-10 / EV-01–07 | Registry, calibration, frozen assignments, paired analysis/allocation | Synthetic/fixture control tests include missing outcomes | 36-task diagnostic and held-out live study |
| SYS-11 / OP-02,04–08 | Admission/drain/quarantine, load/recovery/rollback tooling | Local bounded overload and restore drills | Operated SLO/canary/RPO/RTO/scale evidence |
| SYS-12 / EV-08 | Reproducible CLI, manifests and evidence report | Another process reconstructs report from frozen inputs | Independent human rerun/review and Huy transfer evidence |

**VI:** Matrix này giữ hai lời hứa riêng: giao code chạy được và chứng minh trên môi trường thực. Mọi ô chưa đo phải hiện rõ; không dùng “optional” để che một implementation còn thiếu trong scope đã nhận.

## Research and tensor/serving boundaries

Deliver CPU reference mathematics for causal attention, KV storage, cached/full decode equivalence, compute/memory estimates and fixed-envelope allocation. At minimum trace `Q:[B,Hq,T,D]`, `K/V:[B,Hkv,S,D]`, grouped-head mapping, mask, scaled logits, softmax and output. Label dtype/device/layout and measured numerical error against an independent reference. For conventional KV storage, bytes are `2*L*B*S*Hkv*D*bytes_per_element`; grouped-query attention uses `Hkv`, not `Hq`. Allocator overhead, fragmentation and engine metadata are additional.

A runnable GPU benchmark, when provided, checks CUDA/device/dtype availability, pins software/model/config, warms up, synchronizes timing, measures memory, compares numerical output and stores raw samples. Missing GPU returns explicit skipped/blocked status and no throughput number. A CPU cache simulation demonstrates policy arithmetic, not actual paged GPU memory, prefix-cache speedup or multi-node serving. No training module becomes a target-role prerequisite merely because a tutorial can be generated.

**VI:** Tensor trace đi từ chỉ số đến byte giúp hiểu cơ chế; benchmark đi từ hardware thật đến thời gian giúp hiểu performance. Một công thức FLOPs không thay thế profiler, và API token usage không phải FLOPs provider đã dùng.


## Current source gaps retained after consistency review

The delivered reference leaves automatic active-attempt replacement/reconciliation, graph revision and descendant invalidation, new-generation execution, semantic/native context rollover, fair queued admission, full retention/garbage collection and a generalized live repository coordinator unimplemented. The fixture engine and general provider harness are separate source paths; a mock-tested live transport does not make the fixture engine a live multiagent product. Reconciliation/restore and human review depend on separately trusted callers. Full infrastructure cost accounting and operated restore/canary/SLOs remain incomplete or unmeasured as detailed in [08](08-implementation-coverage.md).

`init`, `inspect`, `replay`, `fault`, `evaluate` and `preflight` are **not** `service.cli` subcommands. Available related functions are Python APIs, tests, or the separate `python -m evals` / `python -m compute` entry points. The current inventory intentionally does not erase broader target requirements: source extensions need implementation evidence; live inference, broader task evaluation and GPU results need their own measurements.

**VI:** Một function recovery, một Temporal adapter và một demo chạy được chưa ghép thành autonomous recovery cho mọi task. Ghi rõ phần nối còn thiếu giúp chọn bước engineering tiếp theo, đồng thời giữ code hiện có làm đối tượng học chính xác.

## Course-derived extension contracts — proposed, 2026-10-10

The [pinned course audit](../research/course-audit-2026-10-10.md) selects four additions to existing gaps. These are **design requirements, not implemented APIs or passed tests**. Extend the current runtime, workload registry and analyzer; do not replace them with the course framework, session log, grader, scheduler or tracing vendor. Existing SYS/RT/EV/OP requirements remain normative. No new curriculum modules, benchmark population, deployment platform or primary research question are introduced.

| Extension | Existing owners to extend | Requirements / learning / milestone |
|---|---|---|
| Accepted context projections | `context.py`, provider adapters, `Harness`, artifacts, `RuntimeStore`, recovery | SYS-05, RT-05/06/09; H5; M5 |
| Bounded skill discovery and activation | Strict tool schema, broker, frozen task policy, immutable artifacts | SYS-02/03, RT-01/05; H9; M2/M5 |
| Symbol evidence from one LSP profile | Broker, guarded workspace, execution supervisor, artifact store | SYS-02/03/05, RT-01/03/07; H6 with H2/H7/H9; M2/M5 |
| Failure mining and regression promotion | Existing `evals/`, assignments, workload controls, verifier, reports | SYS-10, EV-01–08; H8/H15; M0/M6 |

Each new persisted schema needs explicit compatibility/migration design under the existing offline writer protocol. Do not silently alter schema 2 or assume rolling compatibility. Keep Anthropic and Nebius protocol capabilities explicit; support for one transformation on one provider implies nothing about another.

**VI:** Bốn phần bổ sung lấp gap đã có. Runtime giữ quyền, artifact giữ bytes, evaluator giữ mẫu số; course chỉ cung cấp cơ chế và phản ví dụ để thiết kế tốt hơn.

### Context: derived state with durable activation

**Bounded implementation, 2026-10-10:** [the frozen per-dispatch contract and addenda](../research/context-offloading-spec-2026-10-10.md) implement deterministic offloading, current-response retrieval and typed recovery with [independent review](../research/context-offloading-independent-review-2026-10-10.md). Acceptance and model intent commit in one transaction; schema 2 is unchanged. A post-commit crash retains in-flight uncertainty. This specializes the wider design below; semantic summaries/native compaction and task-wide mandatory enforcement remain future work. Anthropic offloading is unsupported; its full-history path remains available.

**Purpose:** fit the next request while preserving required constraints, inspectable evidence and provider-valid continuation. Durable history, pending effects and accounting remain intact. Frozen task constraints and current authority are loaded from trusted state, never inferred from summary prose.

**Proposed data:** `ContextProjection` contains schema/strategy version; tenant/task/generation; owner and expected previous projection revision; contract digest; source event/dispatch frontier and history digest; provider/model/adapter identity; system/tools digests; retained protocol artifact references; summary and evidence references; tail boundary; projection digest. Occupancy observations include value, units, source, exact request digest, time and estimate status. Do not label bytes or `chars/4` as exact tokens. Separate occupancy, cumulative usage and monetary liability.

**Wider proposed flow:** a pure planner selects a provider-supported projection → optional accounted summary request → validation → immutable artifact write → fenced transactional activation → build and admit the actual outgoing request from that accepted projection. Activation compares current owner/generation, expected projection revision and immutable source-history frontier. The compaction operation has an explicit identity whose own dispatch/receipt/accounting transitions may advance the event frontier; these cannot invalidate their own successful summary. Reject unrelated intervening source/workspace/authority changes while retaining all compactor events and liabilities. Slow summarization holds no authority transaction. Concurrent progress or owner loss rejects publication; a late bill still settles once. Persistence failure leaves the old projection active, or stops if it no longer fits. Orphaned artifacts grant no authority.

The original `Harness.run` checked `project_context` while building live requests from raw `messages`. [The implemented offloading slice](../research/context-offloading-spec-2026-10-10.md) closes that seam on its explicit context path: the projected messages build the actual request, whose canonical JSON identity is bound to an accepted manifest. The legacy full-history path remains supported. Checkpoints store the accepted projection identity alongside raw protocol/history references; recovery reconstructs the same request under the same adapter/configuration, then separately checks current ownership and effects. An incompatible adapter/configuration requires an explicit transition, never silent rewriting.

**Strategies:** deterministic offloading of eligible old tool bodies into authorized digest references is implemented within the bounded contract above, preserving call/result structure. Next add structured semantic summaries with source references, uncertainty and unresolved work; summary validity cannot be proved by nonblank text or correct headings. A fact observed only in a tool result needs retained content or an authorized reload path. Opaque thinking/signatures stay exact through the supported adapter. If custom projection invalidates continuation, explicitly start a supported fresh session or refuse. Native provider compaction is a separate capability-gated adapter path with its own request, stop-reason and usage normalization tests; it is not the default course integration.

**Admission and cost:** inspect the complete next request before every dispatch, including system/tools, pending results and output allowance. Use a supported count or a justified conservative bound; unknown/stale counts cannot become zero. Keep the byte cap as an independent resource bound. A compactor must itself fit its input/output envelope. Summarizer calls use ordinary durable dispatch IDs, raw artifacts, pre-reservations, settlement and unknown-billing handling. Their cost counts in the same task envelope, including retries and failed attempts. Compaction cannot decrement cumulative consumption.

**Distinguishing checks:** C1 essential fact exists only in an elided tool result; C2 multi-call/retry and opaque blocks remain provider-valid; C3 large new output invalidates a low prior occupancy estimate; C4 malformed/oversized summary, persistence failure and crash before/after activation; C5 accounted summary activates once despite its own receipt events, while unrelated progress or owner loss rejects it; C6 lost response retains compactor liability; C7 accepted projection is exactly what the next request uses; C8 recovery reproduces its digest without clearing unresolved effects. Semantic evaluation must activate compaction first, then issue a separate recall/action probe whose request excludes the original raw source messages/tool bodies. The retained fact may appear in the accepted summary or arrive through tracked authorized retrieval; freeze summary-only versus retrieval-assisted mode and do not disclose the answer in the probe. An answer produced before compaction is not evidence of retention afterward.

**VI:** Ví dụ tool thấy constraint “giữ timezone UTC” rồi output bị offload: request sau phải giữ constraint từ nguồn có thẩm quyền hoặc đọc lại artifact. Summary nói “đã xong” không thể chuyển task sang done. Crash sau khi tạo summary nhưng trước commit chỉ tạo artifact chưa được dùng, không tạo state mới.

### Skills: immutable instructions without capability escalation

**Capture, broker and accepted disclosure steps2–4 implemented, 2026-10-11:** [frozen step-4 specification](../research/skills-disclosure-spec-2026-10-11.md), [independent review](../research/skills-disclosure-independent-review-2026-10-11.md), [verification](../research/skills-disclosure-verification-2026-10-11.json) and [exact request trace](../docs/06-reference-code-reading-guide.md#accepted-skills-catalog-request-and-resource-authority). Preserve [the full frozen skills design](../research/immutable-skills-spec-2026-10-10.md), [capture contract](../research/immutable-skills-capture-spec-2026-10-11.md) and [broker-v1 contract](../research/skills-broker-spec-2026-10-11.md) as separate versioned boundaries. New `accepted_skills_v1` uses context manifest/projection schema2 and adapter `context_skills_v1`, while RuntimeStore remains schema2. Both frozen skill capabilities, explicit capture/config/context and an exact supported scripted/native Nebius adapter are required. Catalog metadata is untrusted system suffix data; loaded body/resources remain exact ordinary tool results. Acceptance binds their state, source history and actual request bytes. A newly successful load cannot authorize a same-response resource read: the call's accepted source state must already name the primary. Known retries reuse their original accepted state; new requests derive current state. Step5 now implements [typed post-turn checkpoint/fresh-owner recovery](../research/skills-recovery-spec-2026-10-11.md): schema3 harness_skills_v1 separates skills_after_turn from prior accepted state, retains exact provider history and original load provenance, and restores under fresh current authority. Missing historical proof fails closed. No broker-v1 promotion, implicit model/provider switching or new capability follows. Paid execution stays disabled.

**Purpose:** progressive context disclosure: compact catalog → selected instructions → selected resource. This reduces irrelevant prompt content while preserving package identity. Loading instructions never grants tool, network, filesystem or publication authority.

**Frozen runtime seams (step5 has its own implemented contract):** use the exact typed signatures and closed records in [the immutable-skills contract](../research/immutable-skills-spec-2026-10-10.md#tools-prompt-identity-and-accepted-context). Immutable discovery produces catalog/package snapshots; `load_skill(catalog_digest, package_digest)` returns the body/resource manifest; bounded `read_skill_resource` additionally binds catalog, package, path and byte range. Package identity binds origin/scope, source revision, format profile and manifest/body/resource hashes; catalog identity also binds configuration and catalog revision. Catalog metadata is attributed untrusted data. Initial policy rejects ambiguous duplicate names and requires explicit scoped selection rather than silently shadowing a trusted installed package.

**First capture profile implemented:** strict PyYAML 6.0.3 event parsing validates required metadata and directory/name identity, preserving optional metadata as data; descriptor-based reads publish scoped immutable artifacts and revalidate captured associations. This is a restricted text-only profile, not full Agent Skills compatibility. Accepted-request disclosure is delivered under the separate step4 contract; typed skill-aware recovery is implemented under the separate step5 contract. Configured offline scripted broker loading retains its step3 contract. No automatic script execution, package installation or hot reload. `allowed-tools` metadata cannot enlarge the task's frozen capability set. Activation consumes the advertised snapshot; changed bytes require explicit rediscovery. The first profile reads bounded bytes directly from verified scoped resource artifacts. Materialization, workspace/origin fallback and script execution are deferred; an output directory convention grants no write access.

**Wider future bounds (superseded for the first one-package slice by the frozen specification):** at most 32 discovered packages, 64 KiB per source manifest, 32 KiB activated body, 16 KiB total catalog, 64 resources per package, depth 4 and 4 MiB total resource bytes per package; YAML depth 8 and no aliases. These are engineering starting limits, not measured optimums. Reject symlinks, nonregular files, traversal and oversized inputs before consumption. Bounded reads must operate on verified handles/snapshots; a prior `resolve()` check alone does not close a replacement race. Escape metadata syntax but do not claim that escaping removes semantic prompt injection.

**Evidence limit:** Capture covers pure S1/S6 subsets: no execution/capability mutation and snapshot membership/scope/bytes. Broker step 3 separately covers ordinary receipt commit/orphan/duplicate boundaries, current-owner/source/frontier checks and bounded direct provenance. Its independent review repaired a duplicate returned by concurrent intent creation, malformed nonobject-result handling and an unbounded action lookup; five distinguishing controls passed. Step4 now covers accepted disclosure/resource authority and the S7 prompt/request-identity component while preserving capability identity. Step5 adds bounded checkpoint/recovery A/R evidence under its independent review; full design coverage follows the current register. Observable live-model skill usefulness remains pending. The broader runtime checks below remain requirements beyond the bounded delivery evidence.

**Distinguishing checks:** S1 instruction asks for a forbidden command yet capabilities stay unchanged; S2 malicious manifest/resource symlink, traversal and special file; S3 YAML/catalog/resource exhaustion; S4 body changes between discovery and activation; S5 same-name provenance collision; S6 resource changes after activation; S7 discovery/activation affects prompt digest while capability identity stays fixed. A loaded skill is not evidence its instructions were followed; require an observable task/behavior oracle.

**VI:** Tên skill không phải identity đầy đủ. Catalog quảng cáo package A thì activation phải đọc đúng A; nếu body đổi thành B, phải báo stale. “Hãy chạy script” trong tài liệu là lời đề xuất, broker mới quyết định có quyền thực thi hay không.

### LSP: bounded semantic evidence over an exact workspace

**Purpose:** add definition, references, hover and pull diagnostics as a comparator to existing lexical search. Diagnostics are advisory evidence, never the independent acceptance oracle. Start with one pinned Python server and a declared LSP 3.17 capability profile; defer push diagnostics, arbitrary servers, automatic rename edits and parallel multiplexing.

**Proposed seam:** `query_code(owner, workspace_ref, server_profile, request)` passes the existing broker's capability/schema/dispatch checks. Return `CodeEvidence` with status (`ok`, `empty`, `unavailable`, `stale`, `cancelled`, `protocol_error`), request ID, tenant/task/attempt, workspace tree digest, document digest/version, server incarnation/image/config identity, encoding, bounded payload and full artifact reference. Empty evidence is a valid observed result; unavailable, stale or malformed responses must never masquerade as clean diagnostics.

**Execution owner:** extend the supervisor for long-lived bidirectional stdio; the current one-shot launcher is insufficient. Server creation/reuse is scoped to the authorized attempt and immutable tree, with a startup lock. A server is a process that may load repository configuration: use a trusted pinned recipe, stripped environment, no provider secrets, read-only scoped tree, bounded writable scratch and controlled egress. Account physical environments, CPU/memory/time and uncertain retirement under existing task/service quotas; a sidecar is not free capacity. Server restart reconstructs ephemeral protocol state from artifacts and grants no new authority.

**Protocol profile:** one admitted semantic operation at a time per server, bounded queue and a single stream reader; serialized writes, request-ID correlation and explicit handling/rejection of server requests. Verify initialize capabilities and sync mode before use; send open/change/close according to that profile. Bound queue wait, write/drain, response and shutdown under one absolute deadline. Bound frames/JSON nesting/result count/text/open documents; drain or cap stderr. Timeout/cancellation retires or resets the session under a documented rule, handles late responses, and does not reuse a partial frame as another response. Forced termination needs observed process-tree retirement; unresolved cleanup retains resource exposure.

**Evidence freshness:** initially query immutable tree snapshots. A dependency edit can invalidate an answer even when the queried file is unchanged; bind the entire tree and mark evidence stale against a changed head. Public coordinates are zero-based Unicode code-point offsets with explicit line/end-of-line handling; convert both ways against synchronized bytes to negotiated LSP encoding, initially UTF-16. Reject invalid coordinates. For `a😀b`, `b` has code-point offset 2 and UTF-16 offset 3. Incoming and returned URIs require supported scheme, authority and scope checks; external references do not authorize automatic reads. Full pull reports only initially; without `previousResultId`, an unexpected `unchanged` is a protocol error. Future diagnostic caches/push support need separate version/result-ID contracts.

**Distinguishing checks:** L1 two simultaneous cold requests create one authorized server and serialize correctly; L2 wrong/late response IDs never satisfy another request; L3 emoji/CRLF coordinate round trips; L4 dependency edit or rename makes evidence stale; L5 unavailable versus empty versus malformed/unchanged; L6 blocked writes, stderr floods, frame overflow, timeout and uncertain kill; L7 cross-tenant/root reuse or external URI denied. L8, only when edit enrichment is added: successful edit receipt commits before optional diagnostics, and diagnostic failure cannot make the mutation retryable. Freeze concrete resource limits with the selected server recipe before executable integration.

**VI:** Request ID cho biết response trả lời câu hỏi nào; tree digest cho biết câu trả lời mô tả phiên bản code nào. Cần cả hai. Process LSP được gọi là read-only không có nghĩa nó bị OS cấm đọc secret; supervisor phải cưỡng chế boundary thật.

### Evals: evidence-to-regression inside the existing evaluator

**First implementation contract, frozen 2026-10-10:** [the bounded adapter specification](../research/failure-regression-spec-2026-10-10.md) resolves consistent source capture, exact schemas, two failure types, accounting, pure-data regression controls and separate reviews before code. Its freeze record is retained under `runs/failure-regression-2026-10-10/`. This implemented subset has [independent review](../research/failure-regression-independent-review-2026-10-10.md) and [source-bound verification](../research/failure-regression-verification-2026-10-10.json); [coverage](08-implementation-coverage.md) owns delivery status. The wider extension below remains the target contract, including work not delivered by this subset. Paid execution remains disabled.

**Purpose:** turn development failures and expensive successes into reproducible counterexamples, then test one intervention. Reuse the six calibration and 36 diagnostic workload definitions, controls, `FrozenManifest`, assignments, `Harness`, artifact/usage ledgers, external verifier and `analyze`. The 42 definitions share 13 templates and do not become independent or held-out samples when copied into a regression directory.

**Proposed records:** `FailureEvidence` binds schema, run/assignment/task/attempt, base/candidate/grader/environment identities, source event/artifact references, terminal category, trace completeness, all-role consumption/unknown exposure, lineage/split and redaction provenance. `FailureSignature` adds classifier version, explicit symptom/action/error identity and grouping confidence. `RegressionCase` binds source hashes, minimized fixture, precondition, observable invariant, exact predicate, known-failing/passing controls, lineage, reviewer disposition and actual fix revision. `ComparisonSpec` freezes baseline/candidate versions, the one intervention, cohort, tool policy, schedules, resource envelope and eligibility cutoff. These are proposed adapters around existing records, not new authority tables or a second execution engine.

Begin with bounded read-only local evidence extraction and explicit committed events. Mine verification failures, repeated denials, stale-evidence retries, unknown effects and unusually expensive completed runs within a declared development window. Grouping is hypothesis generation, not causal diagnosis. Review a minimized case before promotion; never let mining rewrite the oracle automatically. Missing/malformed/incomplete traces produce invalid or unknown probe results, not a pass. Validate paths against the exact tree, not basename coincidence. Keep artifact correctness, behavioral predicates and deadline-compliant verified acceptance as separate endpoints.

**Accounting and populations:** retain every assigned attempt in the primary denominator, with infrastructure/missing/unknown categories visible. Conditional model quality is secondary. Parent, child, planner, integrator, reviewer, retry and summarizer model calls share ledger accounting; unavailable usage retains exposure. Report measured infrastructure costs where available and explicitly unknown components otherwise. Telemetry loss cannot alter acceptance or erase bills. Mined regressions are development data; freeze later held-out families/time splits before tuning. A held-out failure used for development retires that confirmation set before another claim.

**Replay labels:** read-only committed-event reconstruction; trajectory counterfactual under an explicit recorded-tool policy; fresh execution from a clean authorized base with independent verification. Recovery is separate and still requires fencing and effect reconciliation. Recorded-tool misses or incompatible requests fail closed; historical responses cannot establish a new patch works. Fresh trials prove workspace isolation and cannot inherit prior replay state. Live comparisons should exercise the supported public submission/runtime path; a private helper-only score has a narrower claim.

**Distinguishing checks:** E1 one success plus one infrastructure failure gives assigned completion 1/2, with conditional quality separately 1; E2 parent 10 + child 7 + summary 3 totals 20 units even after pruning; E3 unknown/duplicate receipts; E4 forged reward, deleted grader, stale passing receipt and late success; E5 empty/malformed trace cannot establish task success; E6 snapshot/history miss and cross-trial workspace contamination; E7 promoted regression rejects a known bad control and accepts a correct control; E8 compaction probe occurs after activation with original raw source messages absent, under the declared summary-only or retrieval-assisted policy. Run an A/A development control before the first one-change comparison; stochastic equality is not expected bit for bit. Retain the existing primary 1/2/4 scaling and fixed-N allocation research thread.

**VI:** Một pass trên hai assignment là 1/2 dù lần thứ hai lỗi hạ tầng. Tiền vẫn là 20 sau khi transcript bị rút gọn. Probe “không đọc sai path” có thể pass khi agent không đọc gì, nên không thay được oracle kiểm task đã giải đúng.

### Bounded implementation order and exit

1. Add the local failure-evidence/regression contract and distinguishing controls to existing evaluation/tests; no live model or extra benchmark needed. This establishes the measurement surface used by the other extensions.
2. The bounded deterministic context projection, exact dispatch integration and fenced activation/recovery slice is delivered; consult its [verification](../research/context-offloading-verification-2026-10-10.json). Its evidence uses scripted/mock providers. Add accounted semantic summaries only after these boundaries pass; native compaction remains a separate capability-gated slice.
3. Immutable capture(step2), separate broker-v1 loading(step3) and [accepted disclosure(step4)](../research/skills-disclosure-spec-2026-10-11.md) are implemented in dependency order. Step4 exercises catalog/tool/prompt/provider-context identity against actual mock HTTP and separates load receipt, accepted-request disclosure and current-owner authority. Preserve broker-v1 records without promotion. Step5 post-turn checkpoint/fresh-owner recovery is implemented under [its frozen specification](../research/skills-recovery-spec-2026-10-11.md) and [independent review](../research/skills-recovery-independent-review-2026-10-11.md). The October10 candidate retains its dated identity.
4. Add LSP fake-transport tests and supervised lifetime, then one pinned-server integration and freshness/encoding checks. Optional edit enrichment follows durable edit-result tests.
5. Evaluate one extension at a time on development assignments under fixed aggregate budgets. Promote only with preserved SYS/RT/EV/OP controls and measured benefit or a documented correctness need. No mandatory extra scaling pilot, hosted vendor stack or GPU experiment.

Each slice needs source, failure tests, exact evidence references and an updated coverage entry before its implementation claim. This ordering does not complete automatic recovery, replanning, general live coordination or operated SLOs. Learning still begins at H0 and reaches these mechanisms within the existing H5/H6/H8/H9/H15 sequence; no human mastery evidence is prefilled.

This is the order within the course-derived extension work. It does not override the separate [hackathon profile](../hackathon/README.md), add these features to its required deliverable, or postpone its live repository/verifier access gates.

**VI:** Bước engineering tiếp theo là regression/evidence nhỏ để các thay đổi sau đo được. Bước học tiếp theo vẫn là H0. Hai đường tiến độ khác nhau, cùng dùng một codebase và không chờ em giả vờ đã master trước khi AI được build.

## NVIDIA coding tools specialization

**Design and staged implementation, updated 2026-10-11.** NV-S0's CPU numerical foundation and the separate trusted authored GPU qualification probe are implemented; CUDA measurements remain pending. Shared immutable-skills foundations are delivered, while NV1 generated-kernel execution and NV2/NV3 profiler/intervention-specific work remain unimplemented and unmeasured. [Readiness](../research/system-readiness-plan-2026-10-11.md) owns the current bounded scope. [Verification](../research/nvidia-s0-verification-2026-10-10.json) and [independent review](../research/nvidia-s0-review-2026-10-10.md) own the CPU evidence. The [NVIDIA role audit](../research/nvidia-role-alignment-2026-10-10.md) selects Senior Research Engineer — AI Coding Tools, advertised Level 6. These three refinements reuse C1–C6, H0–H15, M0–M7 and existing SYS/RT/EV/OP ownership. They extend the role-specific evidence contract; they do not replace the Anthropic scaling study or enter the deadline-bound hackathon deliverable. API inference remains sufficient for the coding model. Hardware measurement is necessary before claiming the NVIDIA performance specialization; self-hosted inference and training remain separate decisions.

**VI:** Ta thêm đường nối agent → CUDA candidate → oracle/profiler → revision, không tạo service thứ hai. Các invariant về authority, accounting và verification áp dụng cả khi tool chạy GPU.

### Ordered implementation slices

**Execution decision, 2026-10-10:** begin with the smallest numerical reference, independent tests and review. This engineering order is separate from H0–H15 human mastery and the hackathon release queue. A pure CPU mathematics slice need not wait for compaction, LSP or skills.

| Slice | Dependency and output | Evidence boundary |
|---|---|---|
| NV-S0 Numerical reference | Frozen RMSNorm semantics → independent CPU oracle/eager implementation → identity-bound observation → wrong-output controls | Delivered and CPU-tested; local numerical evidence only, without generated execution, GPU timing or RuntimeStore acceptance |
| NV-S1 Isolated GPU recipe | NV-S0; concrete build/loading, trusted measurement, resource/retirement/health mechanisms and permitted resource envelope | Authored trusted-probe CPU/schema preparation is implemented; actual CUDA remains unmeasured. Generated-code build/isolation/retirement are still unimplemented; this does not complete NV-S1. Python intake/verifier guards are not widened implicitly |
| NV-S2 Agent optimization loop | NV-S1 plus explicit integration with existing intake/broker/authority/verifier | One exact candidate through build, final checks and timing; API inference sufficient; no MCP prerequisite |
| NV-S3 Knowledge and profiler intervention | Knowledge/skills after immutable package contracts; profiler after NV-S1; controlled benefit study after NV-S2 | One intervention at a time. Thin MCP wrapper follows working broker operation; LSP remains a distinct protocol |
| NV-S4 Reviewed data and use | Actual development records plus the previously specified failure-evidence/regression adapter and M7 reproduction | Reviewed lineage/data proposal and independent use; no automatic training or held-out promotion |

The bounded two-case course-derived regression/evidence adapter is now the delivered shared foundation after NV-S0; GPU boundary design can progress independently. Its data predicates do not constitute fresh repair correctness, GPU evidence or full NV-S4 delivery. Context/skills follow their existing dependency order, not a new parallel implementation. A stage starts when its engineering prerequisites are supported, not when filenames exist. Model specialization and self-hosted inference remain later hypothesis-driven decisions. Hackathon required repair/access/submission work keeps priority. The NV-S0 delivery adds only the compute reference/tests plus documentation/evidence; no paid API/GPU or deployment. [Coverage](08-implementation-coverage.md) owns actual status.

**VI:** S0 định nghĩa “đúng là gì”; S1 định nghĩa “thực thi và đo ở boundary nào”; S2 mới nối agent vào. Các nhánh knowledge và evidence có thể chuẩn bị song song đúng dependency. Plan nhất quán không có nghĩa mọi stage đã xong.

### NV-S0 frozen CPU numerical contract

**Purpose/owner:** `compute/rmsnorm.py` owns pure numerical semantics and local comparison; caller owns tensors; artifact helpers own digest encoding; RuntimeStore authority is untouched. Follow the independent scalar/eager split in `compute/attention.py` and reuse `service.artifacts.digest_bytes`/`digest_json` plus applicable `evals.validation` primitives. Reference semantics are checked against [PyTorch 2.14 RMSNorm](https://docs.pytorch.org/docs/2.14/generated/torch.nn.RMSNorm.html); local environment is Python 3.12.11/PyTorch 2.14.1, CUDA unavailable. Fixed epsilon below avoids the library's dtype-dependent default.

**Supported v1 envelope:** contiguous CPU strided FP32 `x[R,H]` and `scale[H]`; `1 <= R <= 64`, `1 <= H <= 4096`; finite `abs(x) <= 10000`, `abs(scale) <= 100`; fixed `epsilon=1e-5` inside the square root. Inference only: inputs/output must be exact `torch.Tensor` instances with `requires_grad=False`; subclasses are rejected before dispatching tensor operations. Supported lazy-negative views are read as their logical values, including during byte hashing. Reject unsupported dtype/device/layout/rank/range rather than cast, copy to another device or broaden support. No input mutation; returned reference/eager tensors own separate storage. No caller-configurable tolerance or epsilon. These type/gradient/logical-byte details clarify the v1 boundary during review without widening the numerical envelope.

**API:** `rmsnorm_reference(x, scale)` returns CPU float64; `rmsnorm_eager(x, scale)` returns CPU float32; `check_rmsnorm(x, scale, output)` computes its own reference and returns an advisory numerical observation; `rmsnorm_counterexample()` returns a bounded JSON-safe teaching trace. `python -m compute.rmsnorm` prints that trace; the existing default compute CLI is preserved. No dynamic import or execution of candidate code/callables.

The oracle converts exact FP32 values to Python floats and independently loops with `math.fsum(v*v for v in row)/H`, `math.sqrt` and scalar scaling. Eager arithmetic uses FP32 square/reduction/normalization/scale. Do not round the oracle to FP32 before checking. Elementwise acceptance is `abs(actual-reference) <= 1e-5 + 1e-4*abs(reference)`. These are frozen development tolerances, not measured GPU tolerances. Unsupported input raises `ValueError`; malformed/nonfinite output produces `outcome=invalid` with an explicit reason and null numerical metrics. A valid output is `pass` or `fail`, with failure count and maximum absolute error. Candidate output must also be contiguous CPU FP32 with exact shape and independent input storage.

Observations bind schema/contract/oracle versions, contract digest, exact input/output digests, shapes/dtypes/device, tolerance and verdict. Tensor digests use canonical metadata and exact bytes with explicit byte order; no rounded JSON numeric hashing. Unsupported output may have no digest; record that explicitly. An observation identifies supplied tensor bytes, **not which executable produced them**. It is not a `NumericalReceipt`, cannot grant task acceptance and contains no invented task/build/device-execution identity. Caller mutation after return cannot alter the saved observation. CPU evidence emits no speedup, GPU measurement or accepted-task field.

**Distinguishing tests:** hand-derived `[1,2,2]/sqrt(3+1e-5)`; nonunit/negative/zero scale; zero rows; width1 and widths3/31/33/257; multiple rows/max magnitudes/fixed-seed bounded random cases; omitted scale, bad tail/reduction and epsilon-outside-root rejected on distinguishing fixtures; invalid shape/dtype/layout/device/nonfinite/range; input bytes unchanged and no result/input storage alias; one changed input/scale/output changes its digest. All observations serialize as finite JSON. Reference/eager/oracle tests remain separate from later GPU and hostile-code tests.

**VI:** Oracle và eager đi hai đường tính khác nhau để tránh cùng sai vì một helper. Với `[1,2,2]`, tổng bình phương là9, mean-square là3; epsilon phải nằm trong sqrt. Observation chỉ nói các bytes output này khớp phương trình trong tolerance, chưa chứng minh agent hay binary nào tạo ra chúng.

### NV1 An independently measured GPU coding workload

**Purpose and initial scope:** demonstrate an agent making one performance-oriented code change whose correctness and benefit can be independently assessed. Initial design candidate: contiguous FP32 row-wise RMSNorm, `X[R,H]`, scale `g[H]`, positive frozen `epsilon`, output `Y[R,H]`, with `Y[r,h] = X[r,h] * rsqrt(sum_j X[r,j]^2/H + epsilon) * g[h]`. Freeze finite input range, supported dimensions, accumulation precision, tolerance, aliasing and unsupported cases before implementation. Begin with one CUDA C++ implementation and Python control plane. Reject unsupported dtype/layout explicitly. Select a pinned real consumer before claiming application benefit; a standalone operator experiment has only operator-level scope.

**Owners and records:** the existing workload registry owns a `GpuWorkloadSpec`; trusted build/verifier code owns `GpuBuildReceipt`, `NumericalReceipt` and `PerformanceReceipt`; artifacts own bytes; RuntimeStore owns authority/resource exposure and acceptance. These are proposed extension schemas, not implemented classes. Bind task/attempt/dispatch, immutable source/candidate digest, compiler flags/toolchain/image, binary digest, oracle and input-family identities, GPU model/device/partition, driver/runtime, benchmark version, timing boundary, limits and status. Return bounded observations to the agent; complete evidence remains in authorized artifacts. A profiler report is advisory and cannot manufacture a passing receipt.

**Execution path:** scoped issue → agent patch → guarded candidate snapshot → isolated build → public development checks → optional profiler evidence → revision → fresh trusted final checks → clean timing → existing review eligibility. Worker-visible checks may be repeated within budget. Final cases and expected answers stay outside worker scope; repeated final feedback used for tuning retires that set as held-out evidence. Verify source-to-binary identity at the final boundary. The Python-function verifier and current text-source intake do not already support `.cu` files or this build/measurement path; add an explicit bounded recipe and compatibility review rather than widening their guards silently.

**Hardware boundary:** a GPU worker needs an explicit supervisor profile with device identity, exclusive measurement admission, bounded CPU/RAM/VRAM/time/disk, no model secrets/control sockets and controlled egress. GPU profiling privileges and driver exposure are a distinct boundary review; never enable host-privileged execution as an automatic fallback. Use a dedicated disposable worker for generated GPU code under the declared threat model. Local container tests do not prove GPU isolation. Cancellation or CUDA faults require observed process/device-work retirement; uncertain cleanup retains physical reservation and bill exposure. Before reuse, a failed health check quarantines the worker. Numerical tests or sanitizer success do not prove absence of every unsafe behavior.

**Preimplementation freeze:** choose concrete supported mechanisms for device/VRAM limits, retirement/health checks, profiling permissions and trusted measurement. Generated CUDA C++ can include host behavior: it must not control the trusted launcher, clocks/events, final expected outputs or receipt writer. Define candidate compilation/loading privileges and an external trusted measurement path that attributes completed work to the frozen binary. Loading unrestricted candidate host code into the measurement authority's process is not independent measurement. If a trustworthy boundary is unavailable, classify timing as untrusted and withhold performance acceptance; binary hashing and stdout parsing alone are insufficient.

**Measurement:** independent CPU/high-precision reference, deterministic edge cases and randomized cases precede timing. Include non-power-of-two widths, small rows, zeros, large supported magnitudes and varied scales. Compare against eager and an appropriate optimized/library or compiled baseline on the same semantics, declaring unsupported baselines. Keep diagnostic profiler runs separate from clean timing. Freeze warmup, repetitions, allocation/cache policy, synchronization and baseline/candidate order; retain raw observations. Measure selected kernel duration and full component-call duration; report build/compile, transfer and allocation boundaries separately. Record starting/peak allocated and reserved memory where exposed. Reuse the audited benchmark's lifetime/accounting lessons, not its claim scope. Profiler overhead, GPU sharing, thermal/power state and clock policy are recorded confounders.

**Endpoints:** correctness, valid speedup `t_baseline/t_candidate`, memory, all-attempt coding success, search cost and time-to-valid-improvement remain separate. Compile failures, sanitizer failures, numerical failures, unavailable hardware and invalid timing are visible categories; they cannot disappear from assigned-task results. Repeated timings are nested within candidate/workload/GPU session, not independent coding tasks. One workload can establish a mechanism, not broad CUDA competence. Do not alter the original 42-definition population or report a public ComputeEval score as held-out confirmation.

**Distinguishing checks:** reject fast-but-wrong output; tail indexing or race errors; stale binary/report reuse; unsupported shape accepted silently; forged stdout timing; asynchronous enqueue-only timing; a missing/partial profiler report interpreted as zero; changed toolchain/driver across arms; candidate access to final expected answers; failure to retire device work before slot reuse. A matched A/A measurement checks the noise floor before one-change comparison. A correct optimization with no measurable improvement is a valid research outcome.

**VI:** Ví dụ R=1,H=3,X=[1,2,2],g=[1,1,1] có mean-square=3; với epsilon dương, output là từng phần tử chia cho sqrt(3+epsilon). Phép cộng/reduction trên GPU phải giữ contract số học đã chọn. Sau đó mới hỏi kernel nào nhanh hơn và phần consumer có được lợi không.

### NV2 Versioned developer knowledge and one profiler interface

**Purpose:** supply facts and diagnostics missing from the model's context while preserving provenance and authority. Reuse the course skill package contract and H6 retrieval; no new memory service, vector database or agent framework. A `KnowledgeManifest` binds permitted source URI/license, retrieval date, exact revision/content hashes, toolkit/API compatibility, chunk boundaries and development/evaluation lineage. Version mismatch returns stale/unsupported. Start with a small local official-document corpus and lexical retrieval; escalate indexing only after a measured failure.

Activate a bounded NVIDIA development skill from that immutable package. Its instructions may suggest a profiler call but cannot change capabilities, target device or resource limits. Implement profile-request and report-read through the existing broker/supervisor first. A narrow MCP stdio wrapper then supplies demonstrable integration for the selected role without blocking the first GPU experiment; it needs explicit capability negotiation, request correlation, output/deadline bounds and process cleanup. Freeze the actual MCP version/schema before implementation. Reuse long-lived transport supervision if available from LSP work, while keeping LSP and MCP protocols distinct. No general remote MCP marketplace or arbitrary profiler command execution is required.

Bind every report to NV1's source/binary/environment identities. Parse supported metrics with units and provenance; preserve unknown fields as non-authoritative data. Nsight Systems timeline evidence and Nsight Compute kernel evidence answer different questions. Host/tool errors, denied permissions and partial reports remain explicit outcomes. Retrieving external text never changes task limits or final oracle content.

**Distinguishing checks:** same skill name with different bytes; stale toolkit docs; an instruction requesting forbidden access; a report for another candidate/device; output overflow; timeout followed by a late response; missing profiler permissions. Use one development comparison with fixed model/budget/tool policy and knowledge on/off, or profiler access on/off, not both treatments at once. Passing interface tests establishes integration; task-quality improvement requires the controlled trial.

**VI:** Skill, MCP và profiler không phải ba hệ thống tự chủ khác nhau. Skill đưa hướng dẫn, MCP diễn đạt operation, broker cấp quyền trong contract đã frozen, supervisor thực thi, report mang evidence về lại agent.

### NV3 Reviewed data promotion from the existing evidence stream

**Purpose:** make a small development corpus inspectable for evaluation and possible later model specialization. Extend the delivered bounded `FailureEvidence`/`RegressionCase` foundation instead of starting a data platform; its two data-invariant controls do not yet supply the GPU/developer-data and independent-use evidence required here. A proposed `DataCandidate` binds permissions/license, task family/split, generator model/settings, knowledge snapshot, exact candidate/build/verifier references, correctness/performance outcomes, trace completeness, transformations/redactions and intended use. `DataReview` records accept/reject/quarantine, reasons and reviewer. External publication or transfer requires separate authorization; local review artifacts stay within this workspace.

Use propose → validate → review → immutable versioned export. Candidate text never chooses its own reward or grading split. Deduplicate by source/semantic family before splitting; record the method and residual uncertainty. Generated siblings stay together. Known-good and deliberately wrong examples test validator sensitivity. Keep hidden tests/answers and nonpermitted/private source out of exported contexts; document contamination concerns for public benchmarks. Preserve rejected and expensive unsuccessful attempts as evidence without automatically making them positive training examples.

H14's exact sampled-token/action-mask contract remains required for compatible on-policy objectives. Missing native token/logprob metadata is unsupported for that path, not reconstructed evidence. A text-based SFT dataset requires a separate declared serialization and objective, with no claim it reproduces sampled action probabilities. A future small fine-tuning experiment needs permitted data/model, fixed untuned baseline, held-out families, equal harness/knowledge/tool access, a frozen compute budget and a learning hypothesis. No trainer, GPU fleet or model-gain claim is introduced now. Model specialization remains an explicit unfulfilled role responsibility until demonstrated.

**Distinguishing checks:** correct-looking sample with wrong receipt; absent rights or source; train/test sibling leakage; hidden-answer contamination; malformed/partial trace; changed model/tokenizer; positive label on infrastructure failure; exact replay of a rejected export. Require one reviewed development packet and one independent reproduction/critique using the existing M7 handoff. Human judgment and mastery are recorded only from actual participation.

**VI:** Export chỉ chứa thứ có provenance và quyền sử dụng rõ. Một trace dùng để debug không tự có cùng điều kiện với training data. Chuỗi này tạo cơ sở để nghiên cứu model tốt hơn sau này; chưa có training run thì vẫn ghi chưa có.

## Offline release identity and installed acceptance

[The frozen October10 release contract](../research/offline-release-spec-2026-10-10.md) specializes packaging/reproduction within the existing M7/OP evidence contract. Freeze selected current source, lock and release scripts before construction; retain prior artifacts unchanged; construct fresh source/wheel outputs; install only hash-checked local base wheels into an isolated outside-checkout environment; exercise actual installed product paths. [Dated October10 verification](../research/offline-release-verification-2026-10-10.json) and [independent review](../research/offline-release-independent-review-2026-10-10.md) record the measured slice. Two independent AI runs on the same machine are not fresh-machine, human, live-model or operated production validation. Public dependency preparation is explicitly separate from offline acceptance. No runtime/schema/workload or paid-execution contract changes.


## Readiness implementation boundaries — 2026-10-11

[The dependency plan](../research/system-readiness-plan-2026-10-11.md) records four frozen additions and their reviews. `skill_recovery.py` owns bounded typed reconstruction; `admission.py` plus persisted RuntimeStore policy own atomic queued/running caps; `serving_config.py`/`offline_server.py` own only the loopback fixture process; `environment_recovery.py` owns explicit local-Docker journal observation and cleanup. Existing authority, artifacts, harness and actual verifiers remain the execution path. Shared store schema stays2; versioned records carry their own profiles.

The GPU module owns advisory trusted authored measurement only. It never grants runtime verification, device retirement or billing authority. New installed acceptance binds this source separately from the preserved October10 candidate. [Coverage](08-implementation-coverage.md) remains the status authority; broad production requirements above are not weakened.

**VI:** Thêm profile cụ thể giúp biết contract nào đang áp dụng. Service fixture, repair Docker và GPU probe không tự động có cùng quyền chỉ vì nằm trong một package.

## Provider qualification before live conformance

[The frozen qualification spec](../research/provider-qualification-spec-2026-10-11.md), [prepared-state clarification](../research/provider-qualification-addendum-a-2026-10-11.md) and [diagnostic clarification](../research/provider-qualification-addendum-b-2026-10-11.md) define the next delivered G1/G2 preparation slice. Reuse ProviderApproval, Harness, RuntimeStore, native artifacts and accounting; no second evaluator or execution authority. The full manifest digest enters the synthetic probe contract before dispatch. Reports derive from raw receipts, exact native continuation and the durable ledger; handoff rechecks the identical unstarted repair and grants no permission.

[Source review](../research/provider-qualification-independent-review-2026-10-11.md) repaired a demonstrated report-reindex defect. [Verification](../research/provider-qualification-verification-2026-10-11.json) and [installed release](../releases/README.md) retain source identities and failure evidence. The source sequence is spec → independent code/tests → review/fix → installed acceptance → documentation. The remaining essential order is separately authorized actual account/catalog/rate conformance → one useful live repair → public judge/source/video/rights gates. GPU specialization and optional scaling pilots do not displace that path.

**VI:** Gắn digest manifest vào contract khiến report không thể lấy transcript thật rồi đổi tên task/deadline ở index ngoài. Đây là evidence binding; quyền chạy vẫn ở authority và instruction hiện hành.
