# Offline provider qualification and repair handoff

Implemented and independently accepted **2026-10-11**. This is a bounded G1/G2 preparation step: exercise the native protocol through the existing runtime and bind its evidence to one exact unstarted repair. Paid/live execution stays disabled. [Verification](../../research/provider-qualification-verification-2026-10-11.json), [source review](../../research/provider-qualification-independent-review-2026-10-11.md), [current installed candidate](../../releases/README.md).

## What the evidence means

ProviderApproval holds supplied policy/configuration. Qualification records an **offline mock observation**. RepairEngine owns the separate repair task. Neither a successful report nor handoff grants authority. The approval's original `mock` or `operator-verified` label is preserved; `live_observed`, `g1_passed`, `g2_passed` and `execution_authority` stay false. Account/catalog/current prices and useful live coding quality remain unobserved.

**VI:** “Approved” và “observed” trả lời hai câu khác nhau. Mock giúp kiểm tra harness giữ đúng history, receipt và budget; nó không chứng minh account có model hoặc cho phép dùng tiền.

## Run the bounded slice

Use the same source or installed candidate that will own the evidence. First prepare a supported repair using [the existing repair runbook](../../hackathon/05-local-repair-runbook.md); do not run it. Then invoke `agent-lab` in this order, replacing uppercase placeholders with explicit paths and finite future Unix timestamps:

```sh
agent-lab qualification-prepare --output NEW_QUALIFICATION --repair-output PREPARED_REPAIR --execution-deadline UNIX --review-deadline LATER_UNIX
agent-lab qualification-run --output NEW_QUALIFICATION
agent-lab qualification-report --output NEW_QUALIFICATION
agent-lab qualification-handoff --output NEW_QUALIFICATION --repair-output PREPARED_REPAIR
```

The qualification root must be fresh and separate from the prepared repair. Existing preparation is task `running`, node `repair/pending`, epoch0, generation1, with no attempts or effects; the label `running` alone does not mean a worker started. Prepare/handoff read the original database through a read-only WAL-aware snapshot and inspect the already-local immutable image. They execute no candidate code. The probe constructs its own isolated MockTransport and ignores ambient provider credentials. There is no live-enablement flag.

**VI:** Đọc SQLite chỉ từ main file có thể bỏ mất transaction còn nằm trong WAL. Snapshot phải giữ đúng committed state, rồi dùng RuntimeStore trên bản sao để không bootstrap hay sửa database gốc.

## Exact trace and failure rule

The manifest pins approval, all service source paths/bytes and the prepared repair snapshot. Its digest enters the probe's durable contract **before dispatch**. The first response proposes `read_file`; the broker returns the owned37-byte fixture. The second request must contain that exact assistant message, including opaque fields, followed by the matching tool result. The second response proposes finish only; no candidate, verification or reviewer verdict follows.

For the installed synthetic example, input/output rates1000/2000 micro-USD per million tokens, input bound32768 and output cap1024 give one envelope bound `ceil((32768×1000 + 1024×2000)/1e6)=35`; the two-turn budget is70. Each authored reply reports one input and one output token and settles1 synthetic unit. This is mocked usage, not a tokenizer measurement, payment or current price claim.

| Observed path | Synthetic spent | Reserved after local retirement | Next behavior |
|---|---:|---:|---|
| Two valid replies with exact native continuation | 2 | 0 | Evidence can support advisory handoff to the identical unstarted repair |
| First response lost | 0 | 35 | Failed report; no resend and no handoff |
| Started marker without final report | Inspect retained DB | Preserve existing exposure | Refuse a new attempt; retain evidence for inspection |

**VI:** Retire probe chỉ bỏ allowance chưa dùng, không xóa khoản35 có thể đã phát sinh từ request mất response. Có tiền còn lại trong task không đồng nghĩa được phép gửi lại request cũ.

Report reading rechecks current source, exact durable contract, current snapshot/events, raw refs, request reconstruction, native linkage and accounting. A corrupted receipt, edited summary or canonically rehashed manifest fails validation. Handoff rereads the repair binding and writes an immutable advisory record; it does not lock a concurrent future repair start. Changed source/config/task needs fresh qualification, never relabeling old evidence. Use the matching preserved candidate to inspect historical reports. Do not delete a start marker to force retries.

## Source and learning entry points

Read [immutable manifest](../../service/qualification.py#L92) → [read-only prepared snapshot](../../service/qualification.py#L172) → [prepare](../../service/qualification.py#L269) → [durable manifest binding](../../service/qualification.py#L348) → [once-only run](../../service/qualification.py#L486) → [evidence derivation](../../service/qualification.py#L377) → [report](../../service/qualification.py#L542) → [handoff](../../service/qualification.py#L576). The [independent tests](../../tests/test_provider_qualification.py) distinguish ordinary pass, Unknown and relabeled evidence. [Spec](../../research/provider-qualification-spec-2026-10-11.md), [prepared-state clarification](../../research/provider-qualification-addendum-a-2026-10-11.md), [diagnostic clarification](../../research/provider-qualification-addendum-b-2026-10-11.md) own the contract.

This supports H0/H4 state ownership, H9 native protocol, H12 conservative cost and H15 evidence provenance without adding a curriculum module. Human mastery remains unassessed. For a later learning session, predict what should happen if only the manifest deadline changes, or if the repair starts between report and handoff; then trace the exact rejecting owner/check. Do not use the AI-authored test result as Huy's prediction.
