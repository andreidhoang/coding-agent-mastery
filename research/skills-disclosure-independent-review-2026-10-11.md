# Independent review: accepted skill disclosure

Date: **2026-10-11**. Status: **APPROVED for bounded step4 — source, verification, demo and documentation reviewed**. Reviewer owns this report and `runs/skills-disclosure-2026-10-11/review/`; runtime source and maintained tests have separate owners. Architecture authorship and source review are recorded separately from implementation authorship. Paid execution is disabled.

## Contract and evidence boundary

The reviewed [step4 contract](skills-disclosure-spec-2026-10-11.md) is frozen at SHA-256 `5038bcbd54e910b17e3d4d44791b7b878986a0996cf7df17ddd95590201d9949`. Independently checked the current spec and frozen copy against this digest, plus preserved parent `99f5f74959efd592e967f5f57d372a151f74c921972be7eaf214ad2dd112b18f` and broker contract `17bad1776f614d9ecf41e8f42ab5cea182f68ec1526ee285cb2c85aeeb311c9c`. The root's pre-code record captures510 baseline files; implementation/source verification remains pending.

The new proof must distinguish committed load from accepted disclosure. Q0 remains empty after l0; Q1 names l0 and carries its exact body; Q1 can authorize a later resource call. Same-response permission cannot use post-load current state. Exact retries must reconstruct historical requests without sends, publication or new receipts. Complete raw history must match actual authoritative provider and tool result records, not just coherent hashes supplied by the caller.

**VI:** Review kiểm tra ba lời khẳng định độc lập: bytes đúng snapshot, receipt đúng transaction, và bytes thực sự nằm trong request đã chấp thuận. Đổi hash đồng bộ của một manifest giả không đủ vượt qua receipt/history oracle. Đây là đánh giá code và evidence của AI, không phải đánh giá mastery của Huy.

## Independent source review questions

| Surface | Adversarial question and distinguishing evidence |
|---|---|
| Version closure | Can context-v1 broker receipts be relabeled as accepted SkillsState, or a mixed key/version pass? Disabled bytes must remain unchanged. |
| Historical versus current state | After l0/resource/Q2, do original Q0 and Q1 still validate without deriving all current records recursively? Does fresh Q2 require the complete current primary receipt? |
| Source authenticity | Can a coherently rehashed unrelated assistant/opaque field, ordinary result, retrieval result or resource result be accepted while exact l0 remains intact? |
| Source accounting | Can a native succeeded receipt with unknown charge, malformed usage, wrong computed charge or token-bound violation authorize a tool? |
| Store admission | Does v2 preflight bound reads before materialization and do authority transactions recheck exact durable records/frontier without artifact reads? |
| Race/duplicate | Can a duplicate discovered at begin dispatch still send/publish, or can an exact old replay write new request/state artifacts? |
| Resource permission | Can same-response load bootstrap resource access, or can bare digest/equal bytes at another path bypass membership? |
| Admission and offload | Can protected result bodies disappear from actual HTTP payload or evade full-request cap despite a valid projection? |
| Checkpoint boundary | Can direct legacy-looking checkpoint input persist v2 accepted history, or can skills completion silently produce a legacy checkpoint? |

These questions were recorded before source inspection. The results below distinguish source inspection, retained failing controls, repaired behavior and final measured checks. No runtime edits by reviewer.

**VI:** Mutation hợp lý phải mô phỏng lỗi có thể xảy ra: dùng current state thay vì source acceptance, tin caller loaded list, hoặc chỉ kiểm tra l0 mà bỏ qua phần history khác. Test pass trên implementation đúng chưa đủ nếu các phiên bản sai đó cũng pass.

## Findings and validation

Architecture review before freeze resolved exact scripted request shape/full request cap, resource authority, complete history reconstruction, historical retry identity, separate adapter capabilities, and explicit unsupported checkpoint results. The final contract includes exact turn exhaustion return and HTTP raw-body versus canonical request-record distinction. Subsequent source review inspected all seven runtime files against their pre-code originals, including unchanged ordinary receipt mechanics and explicit closed version branches. No remaining actionable source blocker was identified in the supported scope after the repairs below.

Source-reviewed root-owned `scripts/skills_disclosure_demo.py` before execution. Its three native MockTransport requests, same-response denial, disposable origin mutation, exact replay publication traps and whole-snapshot comparison form a coherent trace. Requested stronger explicit assertions for catalog/system/tool advertisement, primary dispatch plus actual receipt identity, independent prompt digest reconstruction, and final durable contract/capability stability; the owner added them. HTTP wire bytes are retained separately from canonical request-record identity. Root subsequently executed the demo on stable source; reviewer audited its retained evidence without rerunning it.

Independent stdlib-only `review/verify_demo_evidence.py` opens the saved SQLite database read-only and verifies actual receipt rows, recursively referenced artifact hashes, captured catalog/body/resource bytes, loaded references, exact native messages/prompt digests and raw HTTP records without invoking production validators or rerunning the demo. It explicitly cannot infer replay's no-publication claim from a single final DB; that assertion belongs to the demo execution traps. The audit initially imposed canonical serialization on retained native response JSON; that reviewer error was corrected because raw provider responses legitimately retain wire serialization. No runtime defect was attributed to it.

### Reproduced findings and repairs

| Finding | Distinguishing observation | Final disposition |
|---|---|---|
| Ordinary results accidentally inherited skills65,536-byte wrapper cap | Existing read_file returned78,000 bytes, and a500,000-byte scripted request budget fit the full request, but next acceptance rejected in `_tool_bytes`; `review/ordinary-result-cap-before.txt` retains1 failed test | Repaired by keeping the skills cap only for skills results and the existing bounded artifact cap for ordinary results; reviewer control passes |
| Earlier failed load rejected after a later successful primary | An invalid_package load followed by valid primary, in either the same response or a later response, failed current derivation because the new already_loaded causality guard was applied to known failures; `review/failed-load-before-primary.txt` retains2 failures | Repaired by applying primary causality only to a correct-package load eligible for already_loaded; both controls pass |
| Accepted broker duplicate ignored its configured catalog selection | Source inspection found `_reuse` validated the original source but did not compare broker capture/config; owner repaired before the reviewer executed its control | Equality check now rejects selection drift; positive rejection control passes. This is a source finding, not a reproduced pre-repair failing run |

Additional final controls independently verify terminal model duplicate rejection for both coherently changed settled charge and billing-unknown receipt. They passed after the owner's duplicate `_model` validation had landed; no prior failing result is claimed. Other author/root/test findings and repairs are separately attributed in their retained records, including incomplete no-load history, malformed value shapes and typed record-cap rejection.

**VI:** Hai lỗi được tái hiện có failure log trước sửa; lỗi catalog được phát hiện bằng đọc code và sửa trước khi chạy control. Không gộp các loại evidence này thành cùng một mức chứng minh. Cap của skill không được vô tình đổi semantics read_file; receipt mới cũng không được làm sai ý nghĩa failure cũ.

### Stable-source reviewer evidence

`review/source-bound-controls.json` binds all seven runtime hashes to the author's stable record and independently records identical before/after hashes for runtime/spec/test/control files. `review/controls-final.txt` and XML show **9 reviewer controls passed in 7.82s**, with no production source edits by reviewer. These cover bounded skills-only Harness/store reads, artifact I/O outside authority transactions, complete record-fingerprint recheck even when the frontier is unchanged, ordinary result cap compatibility, two terminal duplicate accounting cases, configured duplicate catalog drift, and two valid failed-load-before-primary histories. Do not add this count to maintained suite counts as unique coverage without checking overlap. Reviewer scripts passed lint.

Source inspection confirms the historical validator reconstructs source prefixes iteratively and validates direct original primary evidence; it does not derive all current state recursively. New acceptance separately derives current membership and compares it, while exact old request replay keeps saved state and references. Native source validation parses usage and checks frozen envelope charge/token bounds; accepted source permission remains distinct from later loaded state. Store rechecks the bounded record fingerprint and frontier under its transaction. Context planner and validator both protect skill results; native receive retains exact whole-envelope/schema equality. Checkpoint creation transactionally refuses v2 attempts, while existing checkpoint validators retain context-v1 requirements.

Verified source entry points: [historical reconstruction](../service/skill_disclosure.py#L322), [current derivation](../service/skill_disclosure.py#L384), [native source validation](../service/skill_disclosure.py#L152), [store admission](../service/storage.py#L781), [Harness](../service/harness.py#L183), [checkpoint refusal](../service/storage.py#L1260).

Final demo evidence audit `review/demo-final-audit.json`: **3 actual local mock HTTP requests,7 dispatches,7 actual receipt rows,25 recursively referenced artifact files,0 checkpoints**. The database remained unchanged at SHA-256 `dac6c87579ee7785e0a38b6b41dc1cb108528b6ad49c54e8eb8758d4b119375e`. Independently checked accepted loaded counts0/1/1, exact system/catalog and prompt digests, native payload versus stored request identity, original load result,193 captured resource bytes reconstructed from two chunks, origin mutation independence and opaque assistant history. Replay zero send/publication/durable-change evidence comes from the reviewed demo's execution assertions, not an inference from the saved final database alone.

Final demo summary SHA-256: `a787558b889af7e9660f1d4f35a705e4e7f6a94814b8e7169344fb5a54b31ccc`. Independent audit SHA-256: `759fea1cac6a1560dc5c39f531371fdb8a5c3e57780222df55adaedd90843c1d`.

### Final integrated and independent test audit

Read `integrated-tests.txt` and XML: **1,820 passed, 156 subtests passed, 3 skipped, one existing Starlette HTTPX deprecation warning, 194.32s**. XML contains no failures/errors and 1,823 ordinary testcase entries; its aggregate includes 156 subtests. Skips are the physical case-collision fixture on this case-insensitive filesystem and two explicit local Temporal opt-ins. Local PostgreSQL and the existing Docker image were exercised; Temporal was not. Final executable source/tests/data/dependencies match before/after records; the separately recorded workloads README spacing edit does not require a source retest.

Independent test record and retained logs confirm **90 passed in 40.66s**, comprising 86 SQLite/mock cases and four isolated PostgreSQL cases. These 90 are included in the full 1,820 and must not be added to it. Inspected each disposable mutation against final production source and its failure log: trusting submitted state fails because forged membership is incorrectly admitted; using current post-load state fails the same-response `not_disclosed` assertion; dropping the load result before native HTTP fails actual-payload equality. All three fail at their intended oracle, not import/setup errors. Runtime/tests remained unchanged while these checks ran.

**VI:** Số test lớn chỉ có nghĩa khi biết điều gì được đo. Ba mutant cho thấy oracle phân biệt authority giả, thời điểm cấp quyền sai và payload gửi thiếu body. PostgreSQL được chạy thật ở local, nhưng HTTP model vẫn là MockTransport; không suy ra model thật đã hiểu hay dùng skill tốt hơn.

### Documentation, preservation and remaining gates

Reviewed current state, coverage, reference contract, context-selection guidance, H0 packet, source-reading trace, release boundary and related core updates. Current claims separate capture, broker-v1 and accepted step4; they keep typed skills checkpoints/fresh-owner recovery in step5, paid execution disabled and human mastery unchanged. Requested one final correction to the current-state summary: S7 prompt identity/protected offloading is now delivered; the remaining gates are typed checkpoint/fresh-owner R checks and completion of the full parent design. The root corrected that wording before this approval.

Independently rehashed all 510 baseline entries: **487 unchanged; six existing runtime files and 17 Markdown files changed**, with no missing entries. New runtime module, demo and two test files have separate identities. Parent/capture/broker frozen specifications, persistent schema/migrations, dependency locks, historical source/release artifacts, benchmark fixtures and mastery tracker remain preserved. Inspected the documentation checker and its reported 50 documents, 1,054 local links, 252 line anchors and 70 heading fragments without errors; independently verified all 30 rebased source lines against exact current declarations plus the one manually resolved request-validator signature. Historical frozen-spec source anchors retain historical bytes intentionally.

All 17 path/digest evidence references in the reviewed verification record matched their files, as did its ten source/demo/test hashes and the independent before/after source records. The task-owned PostgreSQL cleanup record identifies a single container; an independent `docker inspect` of that exact ID returned No such object. No container prune, provider send, paid action or account operation was used for this review. The root refreshes final document/preservation identities and verification status after this report becomes quiet; the separate reviewer audit JSON binds that metadata version without creating a circular report hash.

Approved scope: this source checkout's explicit scripted/native mock accepted disclosure, receipt-derived state, resource authorization and exact same-owner retry. **Still pending:** step5 typed post-turn checkpoint/fresh-owner recovery, real model usefulness/conformance, a new exported/installed acceptance for this slice, fresh-machine qualification, live/public hackathon gates, GPU execution, production readiness and genuine human prediction/teach-back/transfer evidence. These are separate gates, not inferred from the passing source suite.

Step5 typed checkpoints and fresh-owner recovery remain deferred. Mock HTTP can demonstrate actual native payload routing, not live model skill-following or usefulness. No token exactness, injection immunity, production readiness, hostile isolation or release promotion follows from this slice.
