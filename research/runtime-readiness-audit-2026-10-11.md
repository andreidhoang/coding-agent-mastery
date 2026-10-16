# Runtime readiness audit

Date **2026-10-11**. Source review by root and the independent Astra runtime lane, before the new recovery implementation. Baseline identities: `runs/system-readiness-2026-10-11/before.json`. Source anchors below describe that preserved baseline. The earlier 1,820-test result is historical evidence, not a test run of forthcoming changes.

## Findings in dependency order

| Priority | Inspected mechanism and gap | Required change or evidence |
|---|---|---|
| P1 | `Harness.run` rejects skills restore/pause; skills `save_checkpoint` returns no checkpoint. Disclosure validation reconstructs one owner's history. | [Frozen step5 contract](skills-recovery-spec-2026-10-11.md): preserve pre-request and post-turn states, original-owner receipt provenance and fresh-owner authority. Positive two-/three-owner traces and negative frontier/Unknown controls are required. |
| P1 | `DockerSandbox.__init__` generates a nonce only in process memory. `_recover_owned_instance` correctly requires that nonce, but a new supervisor cannot reconstruct it from a durable provisioning record. | Persist a closed create-intent/nonce/config binding before issuing `docker create`; bind the immutable instance when observed. A duplicate uncertain intent must reconcile, never reissue create. Missing inventory after an uncertain create cannot prove a delayed create will never arrive. |
| P1 | Existing retirement checks distinguish exact immutable container ID from a reused name. `retire_sandbox` accepts trusted supervisor evidence and frees the slot; no general supervisor drives that lifecycle after process loss. | Add a bounded trusted lifecycle coordinator that reconstructs only journaled instances and preserves unresolved slots. It must not settle model charges or replay tools. Use the existing store and artifact evidence rather than a separate authority database. |
| P1 | `recovery_plan` classifies Unknown dispatches, unsettled billing and retained environments, but is advisory. `restore_checkpoint` grants no ownership. | Keep that separation. Automatic continuation is eligible only when physical retirement and effect/accounting evidence permit it. Unknown remote effects without a provider lookup remain an explicit blocked scope. |
| P2 | `ReferenceEngine` uses known frozen fixture edits; `RepairEngine` accepts model proposals within its bounded Python-function protocol. Neither supplies arbitrary repository/dependency-aware planning. | Retain honest product scope. General repository execution requires a separate intake/build/dependency/containment contract and live quality evaluation; it cannot be inferred from fixture service startup. |
| P2 | Graphs are frozen; context is bounded; offloaded bodies are retrievable through accepted projections. Semantic rollover, replanning and symbol-service integration remain absent. | Preserve fixed-DAG and overflow refusal as the selected baseline. Do not widen scope with unmeasured compaction or a second evaluator merely to imitate a public harness. |

**VI:** Recovery có ba câu hỏi độc lập: còn process/effect nào đang sống, còn tiền nào chưa biết, và owner nào được chạy tiếp. Một checkpoint đúng chỉ trả lời phần dữ liệu; nó không tự trả lời cả ba câu hỏi kia.

## Source references inspected

- [Harness source — local-only](../docs/github-snapshot.md#omitted-local-evidence): typed opt-in behavior and save path.
- [Disclosure derivation — local-only](../docs/github-snapshot.md#omitted-local-evidence): one-owner receipt/history validation.
- [Recovery — local-only](../docs/github-snapshot.md#omitted-local-evidence): restore and source-frontier checks.
- [Docker lifecycle — local-only](../docs/github-snapshot.md#omitted-local-evidence): nonce ownership, create, immutable ID recovery and close.
- [Physical retirement — local-only](../docs/github-snapshot.md#omitted-local-evidence): slot/allowance transition.
- [Auxiliary environment reservation — local-only](../docs/github-snapshot.md#omitted-local-evidence): existing capacity owner.
- [Fixture coordinator — local-only](../docs/github-snapshot.md#omitted-local-evidence) and [repair controller — local-only](../docs/github-snapshot.md#omitted-local-evidence): current supported execution scopes.

## Interpretation

The runtime already has meaningful authority, immutable artifact, exact-request, accounting, verification and recovery primitives. The missing work is mostly composition across process and deployment boundaries. Adding more prompts or agent roles does not fix these gaps. Conversely, a lifecycle fix cannot prove model coding quality. The [readiness plan](system-readiness-plan-2026-10-11.md) keeps implementation, hardware qualification, live-model evaluation and operated production evidence separate.

**VI:** Đây là audit theo boundary quan trọng đã đọc, không phải chứng nhận mọi dòng code không có bug. Mỗi thay đổi cần test độc lập và review source cuối cùng; số test tăng không tự làm phạm vi hỗ trợ rộng hơn.
