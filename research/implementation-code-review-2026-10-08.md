# Independent implementation review — 2026-10-08

Reviewer: AI architecture/research role (Astra). Scope: bounded review of the newly delivered `service/` implementation against SYS/RT/EV/OP and [reference specification](../capstone/07-reference-implementation-spec.md), emphasizing false acceptance, replay, resource accounting and recovery. The source was changing during review. Findings below record the inspected pre-fix behavior; implementation-owner fixes require their own regression results before the finding is closed. No human mastery or production-readiness judgment follows from this review.

**VI:** Review tìm được lỗi là evidence về điều kiện cụ thể đã kiểm tra. Sau khi sửa, phải chạy regression đúng counterexample; không xóa lịch sử lỗi để làm báo cáo đẹp hơn.

## Reproduced correctness defects

### R1 — P1: Settled billing blocks later effect reconciliation

At review, `RuntimeStore.finish_dispatch` rejected every new receipt once `billing_state == settled` (original `service/storage.py:424–425`; the body is being repaired). A provider can settle a known charge before an uncertain effect is resolved. The sequence `finish_dispatch(..., "unknown", actual_units=9)` followed by `finish_dispatch(..., "succeeded", actual_units=9)` raised `Conflict: dispatch already settled by another receipt`. Thus a valid later effect receipt cannot clear Unknown, permanently blocking replacement and restoration despite available evidence. RT-04/06/09 require effect knowledge and billing knowledge to progress independently.

**Reproduction:** Executed against a temporary SQLite database and artifacts, allowance 40, dispatch bound 12. Observed the exact conflict above. No repository state was modified.

**Required repair/test:** Allow monotonic unknown→known effect resolution after settled billing while preserving the previously settled amount and charging once. Reject changed charge totals and contradictory known effects. Test both receipt orders and duplicate receipts. Storage owner reported repair in progress during review; closure awaits their regression evidence.

**VI:** Hóa đơn và kết quả operation đến qua hai kênh nên thứ tự không cố định. Chặn mọi receipt sau hóa đơn làm hệ thống mất khả năng học thêm sự thật, dù không còn vấn đề overspend.

### R2 — P1: Producer-declared changed paths bypass node write authority

`accept_candidate` compared the declared `changed_paths` against the node allowlist, but did not reconstruct the actual delta against trusted base bytes. `_manifest` accepted a minimal manifest without required producer/integrity metadata. A candidate could include a changed protected file while omitting it from `changed_paths`, then acquire an accepted candidate pointer. The integrator's later delta check catches some manifestations, but the accepted worker boundary itself falsely certifies scope.

**Reproduction:** Base `{'allowed.py':'old','protected.py':'safe'}`; node permits only `allowed.py`; submitted correct base/tree digests with files `{'allowed.py':'fixed','protected.py':'MUTATED'}` and `changed_paths=['allowed.py']`. `accept_candidate` succeeded and the accepted manifest retained `protected.py='MUTATED'`.

**Required repair/test:** Register digest-checked immutable base bytes through a trusted path; recompute actual changed paths and validate full required manifest fields before acceptance. Test omitted changed paths, deleted protected files, changed base, conflicting owner and missing fields. Storage owner proposed `register_base` and root engine integration; closure awaits their tests.

**VI:** Hash đúng chỉ nói manifest chứa đúng bytes đã hash. Nó không chứng minh bytes đó được phép sửa. Cần so với base tin cậy, không tin danh sách thay đổi do producer tự khai.

### R3 — P1: Lost container-create acknowledgement is falsely declared retired

`DockerSandbox.start` set `created=True` only after `docker create` returned success. If the daemon created a container but the client timed out before acknowledgement, `created` stayed false. `close()` then returned `retired=True` without inspecting Docker. This loses provisioning uncertainty and can leak a physical environment while its supervisor reports quiescence.

**Reproduction:** Mocked the trusted launcher to return `exit_code=-9, reason='timeout'` for creation. After `start` raised, `close()` returned `{'retired': True, ...}`; launcher call count remained **1**, proving no inventory reconciliation was attempted. This is a deterministic crash-window reproduction, not an actual induced Docker partition.

**Required repair/test:** Mark provisioning intent before dispatch, reconcile the stable generated container name on every uncertain creation outcome, and retain unknown retirement unless absence or removal is positively observed. Test timeout after daemon-side creation, failure before creation, failed inventory and failed removal. Root accepted ownership of the repair.

**VI:** Không thấy ACK không chứng minh container chưa tồn tại. Container name phải là identity để đối soát, giống dispatch ID ở provider.

## Additional high-priority findings from inspection

### R4 — P1: Pre-restore trusted callbacks lack incarnation fencing

Worker `_owner` checks service incarnation, but `integrate`, `record_verification` and `publish_review` accepted generation/current-head arguments without a caller incarnation. `quarantine_restore` changed the authority incarnation while retaining task generations. After resume, a delayed pre-restore trusted callback could therefore pass the current-generation checks. Workflow preflight does not close the check-to-write race. This violates the delayed-callback part of RT-02/F13 unless all old callbacks are physically impossible by an independently proved mechanism.

**Recommended compatible repair:** Capture an execution-incarnation token at `RuntimeStore` construction; compare it inside every `_eligible` transaction. Do not mutate that cached token during restore. A new control-plane store is required after reconciliation; old stores remain fenced. Keep operator settlement/retirement paths separate. Test rejected stale store and successful fresh store after quarantine/resume. Recommendation sent directly to storage owner; no closure claimed here.

**VI:** Chỉ đọc incarnation mới từ database rồi tự dùng nó không phải fencing. Caller phải mang identity của lần vận hành mà nó thuộc về, để callback cũ không tự nâng quyền sau restore.

### R5 — P1: Unhandled outbox kinds can starve all later task starts

Storage emits `dispatch`, `candidate_ready`, `verify` and `review_ready` records. Both `LocalOutboxDispatcher.dispatch_once` and `TemporalOutboxRelay.dispatch_once` initially recognized only `start` and `stop_sandbox`; the other kinds stayed `pending_retry` forever. `list_outbox(limit=100)` returns the oldest pending rows, so enough unhandled rows permanently hide later task starts. A fail-closed individual command becomes a global liveness failure.

**Required repair/test:** Define a handler/notification acknowledgement contract for every emitted kind, with durable proof when the effect is already completed. Alternatively select supported kinds independently without abandoning required consumers. Never interpret an uncertain `dispatch` record as authorization to repeat its effect. Seed more than one page of internal notifications and prove a later valid start is processed. Sent to root; awaiting implementation/test evidence.

**VI:** Queue bounded batch không đủ nếu đầu queue chứa record không ai xử lý được. Cần phân biệt notification về effect đã làm với command yêu cầu làm effect mới.

## Material implementation scope gaps at inspection

These are delivery gaps, not evidence that a disabled path executed unsafely. If repaired during integration, report exact new tests and remaining runtime validation.

| Boundary | Observed source behavior | Consequence for claims |
|---|---|---|
| Live model loop | `Harness.run` explicitly refused non-`ScriptedModel`; Anthropic transport existed separately | Live coding harness was absent, not merely unmeasured. Root is integrating an explicit billing-envelope path with mock transport tests; paid inference remains unmeasured |
| Partial attempt recovery | Engine reused a fixed claim ID; retired/expired grants fail `_owner`; duplicate model dispatch was refused instead of loading a saved protocol checkpoint | Completed-branch reuse exists, but process-independent resume of an interrupted branch was not implemented |
| Context rollover | `project_context` retains full protocol history and raises when byte limit is exceeded | Safe overflow refusal exists; automatic evidence-preserving rollover/handoff restoration does not follow from it |
| Graph revision | `set_graph` freezes the first graph and rejects a changed digest | Bounded initial DAG exists; versioned replanning/descendant invalidation is not implemented by this path |
| Verification capacity | `LinuxVerifier.verify` directly constructs `DockerSandbox`; engine invokes it after patch retirement without a store environment reservation | Verification environments, unknown teardown and compute cost are absent from shared physical/budget admission unless integrated separately |
| Terminal failures | Engine verification failure returns snapshot; several exception paths leave execution state running until deadline checks reject future work | Explicit failed-known/exhausted/deadline outcomes and cleanup need a tested terminal transition path |
| Restore evidence | Operator reconciliation initially accepted truthy `actor_fencing`/`effect_reconciliation` objects plus current DB scans | This is a trusted operator attestation, not automated proof of beyond-backup effects or physical fencing. Real restore evidence remains necessary |

**VI:** Từ “durable” phải gắn đúng phạm vi: lưu checkpoint là một phần; dựng process mới và tiếp tục an toàn từ checkpoint là phần khác. Tương tự, DAG cố định không tự chứng minh replanning có invalidation.

## Positive boundaries observed

The implementation uses a serialized authority transaction, database deadline checks, scoped artifact references, broker capability allowlists, duplicate-dispatch refusal, retained uncertain exposure, independent exact-tree publication, and configured bearer principals instead of tenant fields supplied by clients. The Linux verifier keeps expected assertions in a trusted host-side grader and runs candidate operations through constrained Docker RPC. These are meaningful code mechanisms. Their completeness and security remain bounded by the tested configuration and the outstanding findings.

**VI:** Giữ điểm tốt và lỗi trong cùng review giúp biết boundary nào đã có thật và boundary nào cần sửa. Không cần phủ nhận toàn bộ code vì một lỗi, cũng không được dùng nhiều test pass để bỏ qua lỗi đó.

## Review disposition

No P0 was established in this bounded review. R1–R3 were reproduced with disposable fixtures/mocks; R4–R5 follow directly from the inspected authority/outbox code and require distinguishing regression tests. Owners were notified promptly. The review did not run paid inference, a held-out study, GPU benchmarks, a multi-host restore or hostile-kernel tests. PostgreSQL/Temporal/Docker integration results reported by other agents must be linked from the final delivery report, separately from these review observations. Final acceptance must list fixes, residual source gaps and deferred operational evidence; do not mark the complete capstone or human mastery complete from this review.

## Follow-up inspection and repair disposition

The following update supersedes the earlier status descriptions while retaining the original fault provenance. Reviewer inspected the repaired source and independently ran:

```text
.venv/bin/python -m pytest -q tests/test_storage.py tests/test_workflows.py \
  -k 'bill_can_settle or lying_changed or restore_fences or auxiliary or notifications or unknown_outbox'
7 passed, 26 deselected (2.10 seconds)
```

This was a targeted local regression run. The storage owner's separate PostgreSQL result is reported evidence until linked/inspected in the final delivery report; it is not included in the seven above.

| Finding | Follow-up observed disposition |
|---|---|
| R1 billing/effect order | **Repaired for reproduced case.** Settled unknown can become known without changing/doubling charge; direct regression passed |
| R2 actual path delta | **Repaired for reproduced case.** Manifest must include full `base_files`; its hash must match frozen base; actual added/changed/deleted paths are recomputed. Forged delta/base regression passed |
| R3 uncertain Docker provisioning | **Repair inspected; dedicated regression pending at this inspection.** `provisioning_attempted` is set before creation; uncertain acknowledgement now forces named-resource reconciliation. Even observed absence is conservatively unresolved because delayed create could still complete |
| R4 old trusted callback | **Repaired for tested store lifetime.** Cached `execution_incarnation` is compared inside execution eligibility; an old controller cannot integrate/verify/publish after restore. Fresh controller positive path regression passed. Physical fencing and administrator trust remain operational prerequisites |
| R5 outbox starvation | **Repaired for tested command classes.** Dispatchers select supported commands and explicitly consume domain notifications without executing effects. Over-100 notifications and unknown-command tests passed |

**VI:** Bảy regression trên đóng đúng counterexample, không chứng minh mọi failure liên quan đã hết. Ví dụ cached incarnation chặn callback từ store cũ; vận hành vẫn phải ngăn actor cũ mở một controller mới trái quyền.

### Newly identified follow-up risks

**R6 — P1, provider token-bound replay bypass:** In the newly integrated live loop, `within_token_bounds` was initially checked only after a fresh call was persisted as succeeded. If token count exceeded one cap but actual charge stayed within the aggregate reserved bound, first execution raised while a replay loaded the saved response and skipped that check, allowing its proposed tools. Sent to root with the required repair: validate new and replayed responses through one common path, persist terminal/containment state for violations, and test no tool executes on either invocation. This finding concerns the new source path, not a paid live run.

**R7 — P1, checkpoint ordering uses wall time:** New `restore_checkpoint` initially rejected post-checkpoint effects using `dispatch.created_at > checkpoint.created_at`. Equal database timestamps (or a backwards clock adjustment) can hide a later known effect and incorrectly permit rewind. Required repair: compare durable intent sequence to checkpoint event frontier, or retain the exact dispatch-ID frontier in the checkpoint. Sent to root; a same-timestamp distinguishing test is required. This was a source-level finding, not an induced production incident.

**VI:** Replay phải đi qua cùng policy gate với response mới. Còn causal order phải dùng log sequence; timestamp đo thời gian không phải chứng minh sự kiện nào xảy ra trước.

### Updated source-gap assessment

- **Live adapter:** An actual Anthropic path now exists in `Harness.run`, with server-approved frozen integer billing envelopes, prior request persistence, per-dispatch reservation, raw response preservation and mock HTTP tests. Paid-provider execution and the real enforceable rate/token contract remain unvalidated; R6 must be resolved.
- **Recovery:** `service/recovery.py` now reconstructs exact checkpoint workspace/messages/evidence and refuses unresolved effects; `Harness.run(restored=...)` consumes that state. The engine reuses completed branches and an integrated head after verifier interruption. Autonomous active-owner replacement remains a manual restricted path; R7 must be resolved.
- **Auxiliary admission:** `reserve_environment` now counts verifier/integrator slots against service/tenant limits and retains unknown environments; its regression passed. Root engine integration was still underway during this inspection. A duplicate retired reservation cannot authorize new provisioning; each new verifier attempt requires a fresh admitted identity. Compute/billing scope must remain explicit.
- **Still deferred source behavior:** versioned graph replanning/descendant invalidation, new-generation task execution, automatic context rollover and fully automatic interrupted-attempt recovery are not supplied by a frozen initial DAG plus checkpoint reader. These are source gaps, not merely missing load or GPU measurements.
- **Operational validation:** hostile-code security, multi-host restoration, canary/SLOs, paid live-model quality, diagnostic/held-out scaling and GPU behavior remain separate measured gates. The completed reference mechanism tests do not close them.

## Final targeted repair verification

The final targeted inspection supersedes the pending repair status for R3/R6/R7 and auxiliary verifier hookup. Reviewer independently ran:

```text
.venv/bin/python -m pytest -q tests/test_review_regressions.py \
  tests/test_engine.py tests/test_live_harness.py
13 passed in 1.93 seconds
```

- **R3 closed for the reproduced crash window:** the regression observes a named Docker inventory query after creation acknowledgement is lost, refuses to claim retirement from absence, and preserves provisioning uncertainty. This remains a mocked fault test; it does not imply a measured Docker-daemon partition exercise.
- **R6 closed for the reproduced replay path:** fresh and replayed provider responses share the token-bound check; a violation calls `fail_execution` before processing tools. The regression confirms one provider request, one model dispatch, retained actual charge, failed task state and a fenced retry with no tool dispatch.
- **R7 closed for the causal-order defect:** the authority transaction persists `dispatch_frontier` in the checkpoint. Restore checks dispatch identity membership rather than timestamps. The test fixes both clocks at 1000 and confirms a later settled dispatch still prevents rewind; the pre-dispatch restore succeeds.
- **Auxiliary verifier admission is hooked into the engine:** a verifier reservation is committed before execution; the infrastructure container name uses that reservation identity; duplicate grants cannot provision again; successful Linux results require positive retirement evidence before releasing capacity. The no-process fixture backend records a distinct retirement receipt. An exception with missing trusted cleanup evidence conservatively retains its slot for reconciliation.
- **Verification failure now has an explicit terminal path:** the engine records `candidate_failed` through `fail_execution` instead of leaving a known failing verdict as running work.

**VI:** Các regression này kiểm cả positive path và denial: restore trước effect vẫn được, sau effect bị chặn; response vi phạm giữ hóa đơn nhưng không chạy tool; verifier dùng slot thật trong ledger. Khi cleanup mất bằng chứng, giữ slot là kết quả an toàn có chủ đích, không phải proof rằng process vẫn còn sống.

No new P1 was identified in this final bounded pass. R1–R7 are repaired for their reviewed counterexamples, with R1/R2/R4/R5 covered by the earlier seven-test follow-up and R3/R6/R7 covered above. This is not a comprehensive security audit. Remaining source limitations are deliberate and must stay visible: initial frozen DAG without versioned replanning/new-generation execution, automatic context rollover absent, manual active-owner replacement/reconciliation, and a general live-provider harness that is separate from the fixture-specific end-to-end engine. Full infrastructure cost models, paid-provider quality, broader workloads, hostile-kernel isolation, multi-host disaster recovery, canary SLOs, independent human reproduction and GPU validation remain outside these checks. The root delivery report owns the final full-suite and actual PostgreSQL/Temporal/Docker evidence.

## Documentation consistency closeout

The architecture reviewer checked chapter 07 against the final module inventory, `RuntimeStore` public methods, actual API routes and command parsers. Corrected module ownership (broker in `harness.py`, provider/billing/recovery/integration/verifier/reporting responsibilities separated), documented current constructor limits and auxiliary/failure/admission APIs, and corrected `list_outbox(..., kinds=None)`. The service CLI currently exposes only `doctor`, `workloads` and `demo`; evaluation/compute use separate module entry points. The current HTTP surface uses `/tasks`, not the earlier proposed `/v1/tasks` path.

Chapter 07 now labels its requirement matrix as **target acceptance**, points to [chapter 08](../capstone/08-implementation-coverage.md) for current coverage, and explicitly preserves source gaps from current-state: active-attempt automation, graph revisions/new-generation execution, rollover, fair admission, retention/GC and generalized live coordination. It also distinguishes current integration CAS/store-incarnation checks from the unimplemented separate leased integrator epoch, and database decision time from the absent persisted commit-confirmation timestamp. No runtime code changed and no tests were rerun for these documentation edits. Root's final full-suite and backend evidence belongs to the coverage/delivery record rather than being silently substituted for this review's own targeted runs.

**VI:** API inventory phải khớp code đang có để bài đọc từng dòng không dẫn tới function tưởng tượng. Yêu cầu rộng hơn vẫn được giữ, nhưng gắn đúng nhãn target và gap thay vì biến thành thành tích đã giao.
