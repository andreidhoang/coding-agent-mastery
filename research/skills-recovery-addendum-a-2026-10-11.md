# Skills recovery addendum A: known turn without accepted checkpoint

**FROZEN 2026-10-11**, before the corresponding duplicate-path adjustment. Clarifies [the step5 contract](skills-recovery-spec-2026-10-11.md); no permission, schema or state shape changes.

A racing/exact model duplicate may find a known terminal response and results without any accepted typed checkpoint for that completed turn. The read-only duplicate path must not publish a checkpoint to manufacture completion. Refuse with a stable reconciliation-required error and leave artifacts, events, effects, costs and sends unchanged. The original new creator may complete checkpoint acceptance normally. An explicit trusted reconstruction/finalization may later call the typed checkpoint API, with all frozen receipt/history/owner/frontier checks; this is not automatic replay.

An already accepted checkpoint whose acknowledgement was lost is reused exactly. This differs from an orphan checkpoint artifact or a committed load receipt before checkpoint acceptance. Both retain their existing evidence, but neither implies that checkpoint acceptance occurred. Tests must cover both positive acknowledged-record reuse and refusal when the record is absent.

**VI:** Biết tool đã xong không đồng nghĩa checkpoint đã commit. Retry đọc lại record có sẵn; nếu chưa có record cần finalize riêng dưới authority hiện tại, không âm thầm biến nhánh retry thành nhánh ghi mới.
