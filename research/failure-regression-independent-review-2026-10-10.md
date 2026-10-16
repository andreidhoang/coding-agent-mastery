# Independent failure-to-regression adapter review

**Date:** 2026-10-10. **Reviewer:** independent AI review lane, not an implementation author. **Verdict:** accepted for this bounded local engineering slice after repair; no unresolved findings from this review. The coordinator explicitly declared final source before the final checks. Paid execution remained disabled. No human mastery evidence was collected.

The review treats capture as a read of committed authority, evidence as an immutable projection, and regression predicates as bounded data checks. A true predicate proves that the fixture preserves its selected identities/accounting; it does not prove a repaired candidate, a live model result, production readiness or human acceptance.

**VI:** RuntimeStore sở hữu state và tiền. Adapter chỉ đọc, rồi đóng băng các quan hệ identity/cost. Case vẫn pending; AI review là lời khai review riêng, không cấp quyền chạy hoặc accept.

## Contract and method

Reviewed `AGENTS.md`, `context/current-state.md`, H0 reference-runtime packet, the frozen [engineering contract](failure-regression-spec-2026-10-10.md), its original [freeze record — local-only](../docs/github-snapshot.md#omitted-local-evidence), and review addenda A/B frozen before their repairs. Applied the first-principles mentor skill to the ownership/evidence framing. No outside research, provider call or GPU execution was needed for this local engineering review.

Read the added RuntimeStore method, both new evaluation modules, fixture/demo code and focused tests against existing dispatch, candidate, verification, artifact, manifest and transaction contracts. Wrote separate adversarial probes under [independent/ — local-only](../docs/github-snapshot.md#omitted-local-evidence), using disposable databases/artifacts. Existing trusted fixture constructors were reused where appropriate; mutations and assertions were independently chosen. No production/test implementation file was edited by this review lane.

## Findings and disposition

| Finding | Reproduction and significance | Final disposition |
|---|---|---|
| Frontier-sized allocation | Original capture built `list(range(1, frontier+1))` even when rows/bytes were bounded. Code review flagged an OOM path from tiny malformed metadata; a later safe 1,000,000-frontier probe exercised the repaired bounded path, not the original allocation. | Repaired; final independent control passes |
| Filename mistaken for scope | Runtime accepted a candidate file literally named `task_id`, but capture recursively treated the filename as a scope field and rejected it. Supported `tenant_id`, `task_id`, `recorded_at`, `time` filenames now form a separate control. | Repaired; final independent control passes |
| Contradictory direct immutable records | Canonical, correctly hashed `FailureEvidence` accepted mismatched subject billing/generation/node/attempt, an out-of-window selected event, a succeeded selected ledger dispatch, and inconsistent dispatch/attempt owners. Predicates remained true. | Repaired; final independent control passes |
| Whole-task causal gaps | Removing an unselected receipt or changing its intent/receipt identity left whole-task evidence eligible. Selected missing receipts were classified as invalid instead of incomplete. | Repaired; final independent control passes |
| Candidate causal disagreement | `head.integrated` revision/parents could disagree with the candidate while evidence remained complete. | Repaired; final independent control passes |
| Strict metadata integers | Boolean `history_start` was accepted as integer1. Count checks also lacked strict type validation in source review. | Repaired; final independent control passes |
| Malformed source crashes | Malformed contract identities, selected states, task shape and owner shape leaked `ValueError`, `AttributeError` or `Fenced`, rather than producing frozen invalid evidence. Coherent future owner generations exposed a later projection variant. | Repaired; final independent control passes |
| Unavailable accounting emitted zero | Failed owner/ledger projection dropped rows and could label zero as whole-task totals. Root froze addendum A before changing to explicit null totals and `missing_source`. | Repaired; final independent control passes |
| Artifact aggregate/read and direct-record limits | Ten tiny-declared refs with an injected 8MiB-per-call reader caused 80MiB of returned reads; direct eligible records also accepted a verified artifact above 8MiB or verified aggregate 40MiB. | Repaired; final independent control passes |
| Direct assignment schema | A complete canonical observation accepted `planned_row={}` and still satisfied its predicate. Direct verification needs the full planned-row schema and row-to-observation base/grader agreement. | Repaired; final independent control passes |
| Synthetic family relabeling | Exact known synthetic repository plus no assignment allowed `family_id=renamed-family` with complete eligible evidence. | Repaired; final independent control passes |

**Probe correction:** the first boolean table-count probe refreshed metadata after changing the count, thereby replacing the boolean with an integer. Its original complete result was not a valid product-defect reproduction. The final probe changes the count after refresh. Boolean history-start reproduction was valid. The source owner ran the semantic probe once during repair and rewrote its current results; initial snapshots were already preserved, and final reviewer runs replace the current records explicitly.

**VI:** Review giữ cả lỗi của probe để không biến một phép thử sai thành evidence. Kết quả trước repair giúp chỉ ra defect; kết quả cuối phải gắn với đúng source hash sau repair.

## Validation and limits

The final [source-bound verification record — local-only](../docs/github-snapshot.md#omitted-local-evidence) ran from **09:17:59 to 09:18:21 UTC** after explicit source-final notification. All seven commands exited 0, all eleven grouped independent assertions passed, all bound source/test/probe/spec hashes remained unchanged, and the complete pre-existing `service/storage.py` byte prefix remained unchanged.

- `.venv/bin/python runs/failure-regression-2026-10-10/independent/run_final.py` executed the five saved capture, semantic, malformed-source, artifact and pinned-read probes; it also independently asserted their expected outcomes.
- `.venv/bin/python -m pytest -q tests/test_failure_capture.py tests/test_failure_evidence.py tests/test_failure_regressions.py` with the explicitly local PostgreSQL opt-in: **170 passed, no skips, 18.26s**. These include the repaired cases, failed-verification generation/tree attribution, Unknown retained/settled accounting, evidence-derived good/bad controls, assignment, lineage, direct immutable construction and authority limits. Counts overlap the implementation lane and must not be added to its totals.
- `.venv/bin/ruff check` over the three production files, new helpers/tests/demo and independent probes: **passed**. The exact file arguments and hashed command logs are in the verification record.

Independent concurrent-writer probes exercised SQLite WAL and task-owned local PostgreSQL: capture paused during its receipts queries, a separate connection committed settlement 9, the current capture stayed byte-identical at frontier 6/spent 0, and the next capture observed frontier 7/spent 9. PostgreSQL used an isolated review schema which was dropped afterwards. The million-sequence malformed frontier stayed incomplete with a measured 62,500-byte traced allocation peak. The artifact post-reader control stopped at four reads/32MiB; direct verified artifact inventories over the per-artifact/aggregate caps were rejected. The valid three-dispatch trace retained 20 units; damaged accounting projected null totals with five explicit missing-source entries. Supported opaque filenames passed.

**VI:** Kết quả đã đo là local controls và 170 tests trên đúng hash, không phải benchmark model. Snapshot frontier 6 giữspent 0 trong khi writer đã commit 9; frontier 7 mới thấy9. Đây là bằng chứng về consistent read, không phải distributed recovery.

Final production/spec SHA256 values (the linked JSON also binds tests, demo and review probes):

| File | SHA256 |
|---|---|
| `service/storage.py` | `8c841dd1f09c97236aa24af57ab927b4fa09ca72a4fb42d02537872e5db8d118` |
| `evals/evidence.py` | `28f8527225cd2652b733e67706188712f9212cb74df7657047b2a0cdaccc0576` |
| `evals/regressions.py` | `a4420219aa650e990ee9e108c84d2d1d35dcf8dcfb82a8a5e70894795d6e52c8` |
| `research/failure-regression-spec-2026-10-10.md` | `dfee96c5ef5fc182c4179833b53a651a43ddff9e1a729203a5bb1bff8e1e6afb` |

Inspected entry points on this exact source: [capture](../service/storage.py#L1626), [immutable evidence](../evals/evidence.py#L443), [extraction](../evals/evidence.py#L550), [predicate](../evals/regressions.py#L155), [case](../evals/regressions.py#L215), and [separate review](../evals/regressions.py#L311).

The authority fingerprint control compares all runtime tables/events/authority plus artifact bytes before and after extraction, predicate/case creation and separate AI review, with the caller-created fixture already stored. Local caller-supplied records, source hashes and reviewer identity remain declared, not authenticated. No analyzer row/denominator, registry population, provider authority, production acceptance or paid-execution setting is changed.

A filename map containing the complete artifact-reference key set (`tenant_id`, `task_id`, `digest`, `size`) was rejected by pre-existing RuntimeStore artifact scanning before reaching this adapter. That attempted control was not counted as a supported-adapter failure; no unrelated runtime repair was requested. Arbitrary-repository execution, adversarial process isolation, distributed recovery, live inference, CUDA performance and authenticated review remain outside this slice.
