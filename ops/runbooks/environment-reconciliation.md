# Recover a journaled Docker verifier environment

Prepared **2026-10-11** under the [frozen environment contract](../../research/environment-recovery-spec-2026-10-11.md). Acceptance status and independent evidence belong to the [readiness plan](../../research/system-readiness-plan-2026-10-11.md). This is explicit trusted cleanup of one known reservation, not automatic task replay.

## Opt in before execution

The existing `ReferenceEngine` Linux branch and supported `RepairEngine` accept an explicit trusted `environment_backend` object. Construct `DockerEnvironmentBackend` for the already configured local Docker daemon and pass it during engine construction. The default remains `None`; old unjournaled rows cannot be retrofitted after a crash. The offline fixture HTTP profile does not start Docker and does not enable this option.

The verifier persists source/config/daemon identity, per-case ordinal, immutable creation intent and a random creation nonce before Docker create. Only the transaction's new winner may create. A duplicate must inspect existing evidence and reconcile uncertainty. The real Docker factory remains in use; injecting a test sandbox factory is a separately labeled mock path.

**VI:** Ghi journal trước create mới giải quyết được mất ACK. Thêm nonce sau khi process đã chết không khôi phục ownership; đó chỉ là đoán lại lịch sử.

## Explicit cleanup after interruption

Use the original authority database and scoped artifact root, one explicit tenant/task/sandbox ID, and a fresh current-incarnation RuntimeStore controller. Reconstruct `EnvironmentLifecycle(store, artifacts, tenant, task_id, sandbox_id, backend)` and call `reconcile_environment(lifecycle)`. Trusted operator code owns those inputs; no model tool or public HTTP route exposes this operation. Keep the database/schema writer protocol and backend configuration unchanged while investigating.

The reconciler seals further instance admission and examines at most32 recorded instances. It verifies the same daemon, nonce, name, immutable image, launch policy and immutable ID before cleanup. Deletion addresses only the recorded immutable ID. It does not accept a name match, a generic `retired:true` assertion or elapsed time as proof.

| Observed durable state | Decision |
|---|---|
| Create intention exists; exactly one matching owned instance is independently verified | Bind its immutable ID, then clean that ID |
| Create intention exists; no matching instance is seen | Unresolved: a delayed create may still arrive; retain physical slot |
| Multiple nonce matches, changed daemon or mismatched launch/ownership | Unresolved; delete neither target |
| Immutable ID already bound; complete inspection confirms that ID absent on the original daemon | Record terminal retirement evidence |
| Every admitted instance terminal and final cleanup sealed | Release the reservation exactly once |
| Historical reservation has no journal | Unsupported; manual investigation under the older recovery contract |

**VI:** “Không thấy nonce N” chưa đủ khi create có thể đang chạy chậm. “Đã biết ID C và xác nhận C không còn” là bằng chứng khác. Đây là lý do code giữ hai state thay vì một Boolean `done`.

Every observation is a bounded scoped artifact. The store checks its identity before transaction entry, then rechecks the journal frontier under the authority lock. Cleanup may retire a revoked task's exact environment through a fresh trusted controller, but cannot revive task capabilities, convert an Unknown model/tool effect to success, settle money or invent a verifier pass. A clean physical environment is only one input to the existing recovery decision.

Preserve the original journal and failed observations. Inspect only the selected nonce/ID; never use broad container pruning or clear the database to make readiness green. If the result remains unresolved, keep the reservation occupied and gather stronger actual evidence. The next model request still needs its own valid checkpoint, current owner, effect/accounting reconciliation and execution authorization.

## Limits

This profile covers a cooperative single-owner local Docker daemon and current-code writers. It does not provide hostile Docker-daemon isolation, GPU scheduling/retirement, remote provider reconciliation, distributed restore orchestration or measured disaster-recovery RPO/RTO. No image is pulled, no provider is called and no paid execution is enabled by the cleanup function. Actual acceptance must name the source, local daemon/image and observed crash window; normal cleanup alone is not a process-loss test.
