# Independent review: immutable skills checkpoint recovery

Date: **2026-10-11**, Asia/Ho_Chi_Minh. Reviewer: architecture lane, independent of runtime implementation; author of the frozen specification. **Review status: both reported defects repaired; the integration owner reran all five unchanged independent controls successfully after the final correction.** Scope is [step5](skills-recovery-spec-2026-10-11.md) and [addendum A](skills-recovery-addendum-a-2026-10-11.md), not a production certification. No paid/live-provider/GPU execution occurred. The reviewer changed only its scratch controls/evidence and review/design documents, not runtime or maintained tests.

## Findings and distinguishing evidence

| ID | Finding | Evidence/status |
|---|---|---|
| SR-P1 | A known model dispatch checked only that its turn checkpoint existed before replaying its tools. After adversarial deletion of the original successful load dispatch and receipt, replay recreated both instead of rejecting missing original evidence. An existing checkpoint therefore concealed a missing durable effect record. | Independent control observed **no exception, two new events, one artifact publication, recreated original load ID**. [Failing log — local-only](../docs/github-snapshot.md#omitted-local-evidence), [original source identities — local-only](../docs/github-snapshot.md#omitted-local-evidence). Runtime author repaired it; independent rerun observed **SkillError, zero events/publications, no recreation**. [Repaired log — local-only](../docs/github-snapshot.md#omitted-local-evidence). |
| SR-P2 | New typed `Harness.save_checkpoint` still materializes `store.snapshot(tenant,task)` to search for an identical checkpoint after already performing the bounded typed lookup. This unnecessarily reads every task record and bypasses the intended bounded collection path; unrelated attempts may be much larger than the64-record skills proof. | Fifth reviewer control rejects whole-task snapshot on the scripted accepted-skills path and fails precisely in `save_checkpoint`. [Log — local-only](../docs/github-snapshot.md#omitted-local-evidence). Fix: retain the old snapshot branch only for skills-disabled behavior; typed save goes directly to the idempotent/race-aware `store.checkpoint`. **Repaired; integration-owner rerun: five passed.** [Final control log — local-only](../docs/github-snapshot.md#omitted-local-evidence). |

SR-P1's repair reconstructs the accepted turn checkpoint and its original receipts before processing any replayed tool. The historical cut is allowed to precede later known same-owner work; it is not mistaken for a fresh resumable checkpoint. Internal `replay_only` admission also rejects a missing original model/tool row inside the final store transaction, closing deletion between preflight and dispatch. The default/disabled request format and store schema are unchanged. Author reports additional deletion-race and missing ordinary-tool controls; the review's measured rerun is the unmodified four-control suite linked above.

**VI:** Checkpoint còn tồn tại không chứng minh mọi receipt gốc còn nguyên. Kiểm tra đầy đủ trước tool và `replay_only` ở transaction giữ invariant: retry chỉ đọc lại evidence; thiếu evidence thì dừng, không tự chạy lại để lấp lỗ hổng.

## Source audit against frozen gates

| Gates | Inspected mechanism and assessment |
|---|---|
| R01/R02 | `skill_recovery.validate_skills_checkpoint_artifacts` reconstructs the original accepted request separately from post-turn state. `reconstruct_history` retains raw supported provider message objects, original-owner call IDs, exact result wrappers and direct primary root. Seed ID advances per owner, without relabeling root ownership. No recursive restore/derive call chain was found. |
| R03 | `Harness.run` rereads caller-supplied restored data from the authoritative checkpoint. `read_skill_proof` checks original attempt owners/generation and consistent seed identity. `preflight_skill`, broker pin and final store transaction require the latest current-owner source and frozen capabilities. A reviewer positive/negative control confirms the same owner cannot import its own checkpoint as a fresh seed before publication. |
| R04/R09 | Closed manifest/payload/post-state keys, exact raw payload bytes and original receipt checks are present. SR-P1 found and corrected an incomplete replay validation boundary. Known turn without checkpoint remains refusal under addendum A; completion restores perform no send. |
| R05 | New checkpoint and new model/tool admission compare internally computed bounded evidence/frontier fingerprints in the authority transaction. They include historical rows, current attempt state and task frontier. Artifact validation occurs before the transaction. The independent transaction-I/O instrumentation passed. |
| R06 | `_model` requires succeeded+settled records and correct native charge from the frozen envelope. `_tool_bytes` requires matching terminal zero-charge receipt. Current Unknown effects prevent fresh admission; restore rejects unresolved covered checkpoint evidence. No code was found settling Unknown solely because a checkpoint exists. Physical replacement remains a separate existing guard. |
| R07 | Store proof collection uses bounded per-attempt queries, direct checkpoint/receipt lookups, one shared visited set and64-record rejection; new intent reserves two rows, checkpoint reserves one. Cycles refuse. At most one bounded attempt batch is materialized before shared-budget merging; no whole-task proof scan exists in `read_skill_proof`/typed restore. SR-P2 identifies a separate whole-task Harness save lookup to remove. |
| R08 | Explicit schema3/kind dispatch; legacy/context and broker-v1 remain separate. Adapter/capability/catalog/config identity is checked, with supported scripted/native Nebius only. |
| R10/R11/R12 | Typed pause/completion/exhaustion preserves cumulative turn budget and exact native reconstruction. Publication-before-acceptance leaves only artifacts; checkpoint failure does not erase receipts. Actual mock HTTP and separate-process tests belong to the independent test lane. This review does not claim live transport, machine crash or provider reconciliation evidence. |

**VI:** Hệ thống có thể restore đúng mà vẫn chưa được chạy tiếp: lease/capability/retirement/accounting là các gate khác. R01–R12 kiểm tra những đường nối đó bằng cả positive trace lẫn negative control, không chỉ kiểm tra có key `skills`.

## Reviewer-run controls

The scratch [control source — local-only](../docs/github-snapshot.md#omitted-local-evidence) reuses fixture setup only; assertions and interventions are reviewer-authored. Authoritative-row deletions/additions are adversarial interventions, not supported operator procedures.

1. Missing original load dispatch+receipt during known model replay: failed before repair; passed afterward with zero mutation.
2. Instrument all available artifact read/write entry points while authority transactions are active: a fresh-owner resource turn, typed checkpoint and restore passed without artifact I/O inside the transaction.
3. Import own checkpoint as a fresh seed: refused before artifact publication and without state changes.
4. Ancestor vs descendant cut: a synthetic ancestor row added after descendant acceptance does not rewrite the historical ancestor; moving it into the descendant's recorded frontier makes restore reject the invalid lineage. Both observations passed without mutation by read-only restore.
5. New typed checkpoint may not call whole-task snapshot: failed before repair; now passes in the integration-owner rerun of the unchanged control.

Measured progression: initial reviewer helper import/path error and wrong physical row-key deletion were corrected; those are retained as **test setup failures**, not runtime findings ([initial collection log — local-only](../docs/github-snapshot.md#omitted-local-evidence), [first setup log — local-only](../docs/github-snapshot.md#omitted-local-evidence)). Corrected pre-repair run: **one failed, three passed**. Independent repaired replay run: **four passed**. Extended bounded-save run: **one failed, four passed**. Counts overlap and must not be summed.

The test-author lane reports203 passes on SQLite+PostgreSQL and five rejected defective copies for its pre-review-repair candidate; the runtime author reports311 passes/34 skips for a later focused gate. Those reports are complementary provenance, not tests independently rerun by this reviewer, and are superseded for final integrated claims by root's source-bound verification. Reviewer controls ran SQLite and native **mock** HTTP only; PostgreSQL coverage is supplied by the independent test lane/root. Source identities for the corrected replay candidate plus scratch controls are [recorded here — local-only](../docs/github-snapshot.md#omitted-local-evidence). Subsequent SR-P2 correction requires refreshed final hashes and the five-control rerun.

**VI:** Giữ lỗi setup và lỗi implementation riêng để log không gây hiểu nhầm. Bốn control pass sau sửa không phải bốn test mới cộng vào203; chúng overlap về mechanism và dùng cùng fixture input.

## Handoff and next slice

The runtime author applied SR-P2's narrow skills-only branch correction. The integration owner then measured **five passed** using the unchanged reviewer controls; the linked final log owns that result. Final source-bound integrated hashes and broader regressions are recorded in the readiness verification. No broader semantic issue was found in the reviewed R01–R12 implementation within the limits above. This post-handoff paragraph is an integration-owner update, not a claim that the reviewer ran later checks.

The environment-journal design was delivered separately in [the environment recovery specification](environment-recovery-spec-2026-10-11.md); root reviewed/froze it with explicit engine configuration and per-action fencing. It fixes a different boundary: reconstructing Docker ownership after supervisor process loss. Skills checkpoints do not supply that physical evidence. Historical source/runs/release artifacts and human mastery remain unchanged.
