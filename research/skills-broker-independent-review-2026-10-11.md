# Skills broker — independent review

Date: **2026-10-11**, Asia/Ho_Chi_Minh. Status: **approved for the bounded scripted broker slice after repairs**. AI engineering review; human mastery unchanged. Paid execution, account redemption and live provider calls are excluded.

The review reads the unchanged October 10 full skills design, October 11 capture contract and source, current-state summary, H0 packet, and current broker/protocol/storage/provider/recovery seams. The review owns this report and `runs/skills-broker-2026-10-11/review/` only. The implementation and independent test lanes own other changes.

## Architecture findings before freeze

1. Existing context version 1 does not bind a catalog or loaded membership. Dependency step 3 can establish ordinary broker receipts and derive current-attempt loaded evidence, but it cannot claim that an accepted model request disclosed a catalog or body. Resource access must remain denied until the later accepted-state integration. Any narrower broker-only fixture seam needs an explicit contract and must not silently promote these receipts into a future accepted state or restored seed.
2. A pinned dispatch is initially copied before its model receipt completes. New skill intent must refresh the authoritative source, require its supported successful response, validate exact proposed call and source linkage, and atomically recheck current owner/latest source. A diagnostic artifact, terminal success with malformed response, another same-task request or constructor-supplied capability list alone is insufficient.
3. Schema 2 already supports sibling dispatch metadata. Closed `skill_call` and its digest belong beside the six existing dispatch parameters, with exact duplicate comparison; neither a new active-state table nor a schema migration is needed.
4. Loaded membership requires both a succeeded ordinary receipt and deterministic result equality against the captured package, original call and provenance. An orphan artifact, failed-known or Unknown receipt, mismatched body/descriptors or an `already_loaded` result cannot create a primary root. A changed catalog must cause rejection rather than disappearing through a filtered receipt scan.
5. Known identical retry can read its original result even after a later accepted response, while a new intent needs the latest accepted source. Current-owner fencing still applies. Unknown/in-flight duplicates cannot run again. Competing first loads need a transaction/frontier check or fail-closed competing-root detection.
6. Read and result caps cover complete canonical wrappers, not only body bytes. Duplicate reads need bounded exact artifact validation; public failures must remain sanitized. Before-receipt failure leaves an unresolved dispatch and/or orphan; an acknowledged-lost committed receipt remains one primary identity with no extra event or cost.

**VI:** Receipt load là evidence đã đọc snapshot. Nó chưa chứng minh request gửi model đã chứa catalog/body, cũng chưa cấp quyền đọc resource. Slice nhỏ phải giữ ba điều đó riêng; recovery owner mới và request version mới vẫn là bước sau.

## Concrete specification review

Reviewed [the broker contract](skills-broker-spec-2026-10-11.md) before implementation. The initial ambiguity between fixed catalog selection and admitting wrong-catalog failed receipts was repaired: a wrong catalog now rejects before intent, while a wrong package under the selected catalog has a deterministic bounded failure. This prevents failed calls from poisoning all later derivation.

The reviewed design also explicitly refuses skill calls on an unconfigured broker before intent, reconstructs mutable nested ToolCall arguments, verifies exact error results, treats succeeded resource records as invalid, recovers original provenance for known duplicates after a later pin, and distinguishes a read-only record inspection from a live owner capability. The bounded SQL API and transaction frontier reserve room for both the new dispatch and its eventual receipt. Existing context-v1 records are explicitly insufficient for future accepted disclosure/recovery.

Architecture approved for freeze after two wording clarifications: valid-package resource calls yield `not_disclosed`; artifact integrity validation can internally read captured resources although no resource chunk is returned. No source/runtime result is inferred from this approval.

## Source review and repaired findings

The frozen specification SHA-256 is `17bad1776f614d9ecf41e8f42ab5cea182f68ec1526ee285cb2c85aeeb311c9c`. Reviewed the four changed runtime files and the root-authored demo against that contract. No provider, context planner, Harness loop or checkpoint integration is inferred from the new broker seam.

| Finding | Repair and distinguishing evidence |
|---|---|
| The common intent path materialized every task dispatch before reaching the new 64-record check. | The skills branch now uses a scoped action lookup with SQL `LIMIT 1`, then the bounded current-attempt reader. An independent control replaces unbounded dispatch listing with a failure and proves a new load still succeeds. [Store boundary](../service/storage.py#L792). |
| A canonical non-object artifact (`[]`, string, integer or null), coherently bound by a succeeded dispatch and receipt, raised `AttributeError` during derivation. | The result parser now explicitly requires an object before accessing fields. All four reviewer controls failed on the original source and pass after repair with stable `SkillError`; failed and passing logs are preserved. [Object gate](../service/skill_runtime.py#L226). |
| Root review reproduced a race where another caller won the same intent after preparation; the first caller ignored the returned duplicate flag. | Execution now checks the returned flag and reloads/revalidates the durable result. An unresolved winner refuses; a committed winner returns its receipt without a second publication. Independent maintained tests exercise both schedules. [Duplicate branch](../service/skill_runtime.py#L315). |
| Root review identified unbounded direct metadata paths and inconsistent ordinary receipt aliases. | Resource paths use the existing bounded lexical validator, and the bounded reader compares every current receipt with the exact dispatch fields, including ordinary records. [Path validator](../service/skill_runtime.py#L37), [receipt comparison](../service/storage.py#L729). |

Source inspection verifies both frozen capabilities, current-owner fencing at intent, source response parsing and exact call linkage, selected catalog consistency, zero-charge ordinary receipts, exact canonical result comparison, direct primary-load references, unresolved duplicate refusal, and full result-wrapper bounds. Artifact publication remains after intent and before the ordinary receipt. Artifact-only snapshot validation supplies original bytes; resource requests in this profile return a bounded denial.

**VI:** Review phát hiện hai nhóm lỗi khác nhau: race có thể làm cùng action bị xử lý lần nữa; artifact sai kiểu có thể làm hỏng đường báo lỗi dù chưa cấp thêm quyền. Test giữ lại cả failure ban đầu và source đã sửa, thay vì chỉ ghi kết quả xanh cuối cùng.

## Measured verification and limits

Reviewer execution: **74 tests passed**, comprising the maintained broker tests at that run and five independent controls. The four final runtime hashes match the implementation owner's stable source record; the frozen spec hash remains unchanged. [Reviewer verification — local-only](../docs/github-snapshot.md#omitted-local-evidence), [test log — local-only](../docs/github-snapshot.md#omitted-local-evidence), [independent controls — local-only](../docs/github-snapshot.md#omitted-local-evidence), [original four failures — local-only](../docs/github-snapshot.md#omitted-local-evidence). Counts overlap with other agents' focused runs and must not be summed as distinct tests. Broader regression and backend results belong to the root's final verification record.

The demo was source-reviewed as three independent real SQLite fixtures for normal load, publication-before-receipt interruption, and lost receipt ACK. Its explicit no-send/no-disclosure/no-recovery claims match the implementation. Final measured demo identities belong to the root's delivery record.

No remaining material finding was identified within this frozen dependency step. Receipt-derived `broker_skill_loads_v1` is current-attempt data evidence. It does not establish accepted catalog/body disclosure, successful resource access, live-model usefulness, provider request identity, checkpoint import or fresh-owner recovery. Those remain later dependency steps; existing historical release candidates and human mastery are not promoted.

## Documentation and final demo audit

Independently inspected the updated entry points, context, curriculum/coverage contracts, release/operations/hackathon notes, H0 packet and reading guide. The current delivery is consistently scoped to explicitly configured offline scripted step 3, with accepted catalog/tool/prompt/provider request construction next and fresh-owner skills checkpoints afterward. The reviewer found three stale lines implying broker loading or its one-package enforcement remained pending; root repaired them. The current source anchors in the new broker trace and refreshed H0 runtime seams point to the intended declarations. Historical release evidence and the H0 human-evidence boundary remain separate.

Read-only verification of the final saved demo independently checked observation hashes, all **38 artifact files**, scoped references, canonical call/input digests, captured body/resource descriptors, actual SQLite dispatch/receipt rows, and direct primary-load identities. All three database hashes remained unchanged. Normal case: **4 dispatches, 4 receipts, one primary**; orphan case: **2 dispatches, one receipt, zero primaries**, with the published load artifact unreferenced; lost-ACK case: **2 dispatches, 2 receipts, one primary**. This audit reads the saved evidence and does not rerun or mutate the demo. Summary SHA-256: `15233742ea1d46690213a6b7ee71efc67497aadbd99700259100897a287ae654`. [Independent artifact/DB record — local-only](../docs/github-snapshot.md#omitted-local-evidence), [verifier source — local-only](../docs/github-snapshot.md#omitted-local-evidence).

The root's broader regression run was still in progress at this documentation audit and had reported a failure requiring investigation. This audit adds no full-suite pass claim; final integrated counts and any repair/rerun evidence belong to the root's final verification record.

## PostgreSQL test-fixture timing review

The first integrated run ended with **1 failure, 1,728 passing tests, 4 skips and 156 passing subtests**. The preserved failure occurred in `test_postgres_database_time_final_cutoff` while `make_task` called `set_graph`, before the claim and before either intended cutoff assertion. Its original host-time deadline was only 0.2 seconds ahead. The database correctly rejected the already expired task. The trace establishes a fixture setup timing failure, not a skill-broker failure or a waived runtime deadline.

Independently reviewed the bounded repair confined to that existing test: select PostgreSQL `clock_timestamp()`, freeze a deadline three seconds later, create and claim the task, sleep only the remaining database-relative interval with a three-second cap, and assert the database clock is actually past the deadline. Then, solely inside the two assertions, set the host clock ten seconds behind the deadline. Both heartbeat and dispatch must still raise the specific database-deadline `Fenced` error. This preserves and strengthens the database-time oracle; runtime code and authority guards are unchanged. Focused execution, the disposable host-clock mutation and the root's subsequent integrated rerun own the final measured results.

Inspected the independent test owner's final logs: the repaired test **passed on local PostgreSQL in 4.02 seconds**. A disposable copy replacing the authoritative database clock with the host clock **failed at the expected missing-`Fenced` assertion**. Runtime and target-test hashes stayed unchanged during these checks. [Focused/mutation record — local-only](../docs/github-snapshot.md#omitted-local-evidence). The root's complete rerun remains the integrated acceptance gate.

## Final integrated outcome

The subsequent complete rerun supersedes the pending integrated status above: **1,730 tests and 156 subtests passed; 3 skips; no failures or errors**, in 194.42 seconds. Independently inspected both [the final text log — local-only](../docs/github-snapshot.md#omitted-local-evidence) and [JUnit result — local-only](../docs/github-snapshot.md#omitted-local-evidence); the repaired PostgreSQL cutoff test passed within that full run. JUnit reports 1,889 total entries, which includes the 156 subtests and three skips rather than 1,889 separate passing tests.

The skips are the physical case-collision fixture on this case-insensitive filesystem and two explicit local Temporal opt-ins. The one warning is an existing Starlette/httpx deprecation warning. The original failed run and its test-fixture timing repair remain preserved above. This successful rerun changes no scope conclusion: the skills delivery remains the configured offline scripted broker seam, with accepted disclosure/provider request integration and fresh-owner skills recovery still pending. Final source/artifact identities and backend enablement belong to the root's delivery verification record.
