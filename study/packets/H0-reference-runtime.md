# H0 reference-runtime packet: trace the entire system

**Prepared 2026-10-08; affected source links refreshed 2026-10-11; AI-authored; human evidence pending.** This is a bridge from the preserved [original H0 packet](H0-system-boundaries.md) to the delivered reference runtime. Its concept is **H0 Trace the entire system** in [the H0–H15 plan](../../docs/02-mastery-learning-plan.md). Since [D046](../../context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates), this packet is reference material for production traces; its assessment table and rubric language are optional. Use [the complete reading guide](../../docs/06-reference-code-reading-guide.md) for later module entry points.

**VI:** Mục tiêu H0 vẫn là biết toàn hệ thống làm gì và ai sở hữu state. Reference mới cho em object thật để trace; không có nghĩa H0 đã xong. Giữ prediction trước experiment học của em, nhưng đừng sửa lịch sử để biến kết quả AI đã chạy thành prediction của em.

## 1. Concepts before source

The [foundations-to-production companion](H0-first-principles-to-production.md) derives these boundaries from state transitions, partial observations and finite resources. Use its exact FIFO trace and current source map when connecting this lesson to serving; keep local fixture HTTP, CLI repair and offline provider qualification distinct.

A request is an intention with constraints. An action is a validated command under explicit authority. An effect is a change to external state. A receipt is evidence about that effect. A candidate is immutable bytes proposed for evaluation. Verification measures that exact candidate under a frozen grader/environment. Acceptance adds the required reviewer decision. Durable intent, transcript, workspace and verifier state have separate owners; each can advance before another commits.

**VI:** Ví dụ model nói “đã sửa phép cộng” chỉ là message. File có thể chưa đổi, hoặc đã đổi nhưng receipt mất. Verifier cũng có thể pass bản cũ trong khi file mới đã khác. Ta cần identity/digest để buộc mỗi phát biểu vào một object cụ thể.

| Object | Producer → consumer | Owner / trust / boundary |
|---|---|---|
| Frozen task contract | API/CLI → scheduler/harness | Authority DB; caller scope validated; client text cannot grant extra rights |
| Current owner tuple | Transactional claim → broker/acceptance | service incarnation + tenant/task/generation + node epoch/attempt; old owner fenced |
| Provider messages and tool blocks | Adapter/harness → next model request | Exact supported protocol representation in immutable artifacts/checkpoints; prose summary cannot replace opaque blocks |
| Workspace bytes | Guarded tool → snapshot/integrator | Separate file state; expected digest prevents editing a stale read; host fixture scope differs from Linux isolation |
| Candidate/tree/head | Worker/integrator → verifier | Immutable artifact identity and head revision; integrator publishes one current tree |
| Verification/review receipts | Trusted verifier/reviewer → authority/report | Exact tree/grader/environment/contract identity; final DB-time eligibility is separate from later review |
| Unknown dispatch/billing | Broker/reconciler → recovery/budget ledger | Effect and charge knowledge are independent; uncertainty retains exposure |

**VI:** Controller là nơi quyết định dispatch; model không tự gọi syscall bằng token. File path/tool arguments từ model vẫn phải qua capability/schema/digest check. Một process exit0 có thể là process nói dối; trusted grader receipt là một lớp evidence khác.

## 2. A tiny state trace to reconstruct

Follow the [claim](../../service/storage.py#L551), [intent](../../service/storage.py#L718), [receipt](../../service/storage.py#L1056), [retirement](../../service/storage.py#L1537) and [budget derivation](../../service/storage.py#L380). Begin with a task limit of 100 units. Claim40 creates attempt allowance40 and occupies one physical slot. Dispatch bound12 moves allowance to28 and reserves12 for the unresolved operation, keeping total reservation40. A lost response leaves effect Unknown. Cancellation revokes generation authority but does not erase liability or physical occupancy. Confirmed retirement frees unused28 and the physical slot; unresolved12 remains. Trusted late actual9 settles once: spent9, reserved0. Repeating the identical receipt cannot charge9 twice.

**VI:** Đây là trace derived từ invariant và test, không phải prediction của Huy. Bài cần tự làm là giải thích vì sao total reservation không lên52 khi dispatch, và vì sao cancellation không làm reservation về0. Tách ba lane: quyền chạy, chỗ máy đang giữ, tiền có thể bị charge.

The distinguishing tests are [Unknown/replacement](../../tests/test_storage.py#L189), [late settlement](../../tests/test_storage.py#L214), and [settled bill with Unknown effect](../../tests/test_storage.py#L441). They establish the exercised reference invariants; they do not show that every remote provider supports exact effect lookup.

**VI:** Khi đổi file edit thành remote issue-create, cần có idempotency/effect identity ở phía remote hoặc cách query receipt. Local journal không tự chứng minh remote chưa tạo issue. Không đủ evidence thì giữ Unknown là đúng.

## 3. Source reading, one transition at a time

Open these methods in order. For each block annotate inputs, trusted identities, state reads, checks, writes, external side effects and crash outcome. Use line-by-line notes only on this small slice first; the full module map is in the reading guide.

1. [validate_contract](../../service/contracts.py#L145) and [submit](../../service/storage.py#L424): client request → frozen contract/digest/task generation; compare an identical retry with changed-body collision.
2. [claim](../../service/storage.py#L551) and [_owner](../../service/storage.py#L353): claim → owner tuple/attempt/physical slot; find which conditions reject stale or over-capacity actors.
3. [Harness.run](../../service/harness.py#L186): requirements → transcript/context → immutable request → durable model intent → response → tool result → checkpoint in the default profile. The explicit accepted-skills profile now writes a typed post-turn checkpoint; [its recovery trace](../../docs/06-reference-code-reading-guide.md#skills-recovery-pre-request-state-post-turn-state-and-a-fresh-owner) distinguishes accepted pre-request state from post-turn membership and fresh-owner authority.
4. [ToolBroker.execute](../../service/harness.py#L63) and [Workspace.replace](../../service/execution.py#L79): validated call → durable tool intent → digest-guarded file mutation → result artifact/receipt. Locate the effect-before-receipt crash window.
5. [integrate_candidates](../../service/integration.py#L53) and [integrate](../../service/storage.py#L1846): branches → conflict-checked tree → head revision.
6. [record_verification](../../service/storage.py#L1905), [publish_review](../../service/storage.py#L1957), [record_review](../../service/storage.py#L2023): passing exact receipt → DB-time eligibility → later human acceptance/rejection.

**VI:** Đừng trace bằng “model → tool → done”. Mỗi mũi tên cần object cụ thể: request digest, call ID, dispatch ID, result_ref, tree digest, verification ID, review ID. Nếu ID đổi, hãy nói đó là attempt mới hay same logical action, và vì sao.

## 4. First experiment on the new reference

For your study, write your prediction before running or reading the selected saved trace. AI delivery checks already exist and should remain attributed to AI. Suggested prediction: if a tool edit changes bytes but result recording is lost, will replay edit again; what will workspace and journal respectively show? Which evidence would change your answer?

**VI:** Dự đoán có thể sai. Giá trị của bài là khi output khác, em tìm boundary đã giả định nhầm. Không chép expected outcome của test rồi ghi là prediction trước khi chạy.

```sh
.venv/bin/python -m pytest -q tests/test_engine.py::test_ambiguous_tool_dispatch_is_not_reexecuted
.venv/bin/python -m pytest -q tests/test_storage.py::test_cancel_preserves_unknown_and_late_settlement_once
.venv/bin/python -m service.cli demo --workers 2
```

The demo outputs a new directory containing `snapshot.json`, `trace.json` and `trace.html`. Inspect one `dispatch.intent` and matching receipt, one immutable candidate and exact verifier receipt, then the `review.published` event. The expected reference endpoint is **review_eligible/pending**, preserving the human-review boundary. The scripted model performs a known reference edit, so this demonstrates orchestration mechanics, not live-model reasoning. The default fixture verifier executes no arbitrary candidate process; selecting a pinned Linux image changes the backend and requires its declared capability evidence.

**VI:** Hãy kiểm tra event và bytes trước khi nhìn report summary. Report là projection tiện đọc; nếu có mismatch, quay lại source identities. “Review pending” không phải lỗi demo; đó là nơi cần decision thực từ reviewer.

## 5. Protocol continuation and current limits

[restore_checkpoint](../../service/recovery.py#L34) reloads exact saved provider messages/evidence and workspace content only after checking contract/generation and the checkpoint owner’s dispatch frontier. It grants no execution authority; a new current owner must be acquired separately. The engine reuses completed branch candidates and the integrated head after later verifier interruption. Active-attempt replacement/effect reconciliation is manual. Explicit local-Docker journaling now supports [bounded physical cleanup](../../ops/runbooks/environment-reconciliation.md); it does not authorize task replay. Graph replanning and semantic/native context rollover remain absent. An explicit [deterministic offloading path](../../research/context-offloading-spec-2026-10-10.md) now binds accepted projections to dispatch and typed recovery; unsupported or irreducible overflow still fails closed. Anthropic and native Nebius harness support are present with approved frozen envelopes and mock HTTP tests, but paid live execution is unrun. [Nebius evidence](../../research/hackathon-2026-10-10/verification.json). Tensor reference and a disabled trusted RMSNorm qualification probe exist; actual GPU/kernel profiling is unmeasured.

**VI:** Checkpoint restore không rewind remote effect. Nếu owner của checkpoint có dispatch mới sau checkpoint, restore helper từ chối tiếp tục như chưa có gì xảy ra. Transcript đầy đủ giúp model biết lịch sử; owner mới giúp hệ thống biết ai còn quyền—hai cái không thay nhau.

## 6. Debugging and transfer without filling human answers

Optionally use the [self-check menu](../../docs/05-mastery-tracker.md#self-check-menu-optional). The worked trace and named defects below are practice material because they reveal parts of the solution. For independent assessment, select a fresh crash point, event order, ownership condition or remote operation without exposing the expected outcome. Use one variant at a time and retain actual human answers in the session note.

**VI:** Đọc trace giúp xây mô hình ban đầu. Muốn kiểm tra em tự hiểu, ta đổi điều kiện thật sự rồi để em dự đoán trước; không dùng đáp án vừa đọc làm bằng chứng độc lập.

Use disposable copies for injected defects; keep reference source and prior traces intact. In a scratch copy, change receipt handling to discard Unknown reservations, or change the duplicate-dispatch path to rerun unresolved edits. Predict which existing test rejects each defect and why. Trace the invariant back to its exact source expression. Do not repair by merely deleting the assertion.

**VI:** Một test đỏ hữu ích vì nó phân biệt hai cơ chế. Nếu chỉ sửa số expected cho pass, em đã thay oracle. Hãy giải thích người dùng hoặc ledger thấy gì sai trước khi nghĩ cách sửa code.

| Human evidence field | Entry |
|---|---|
| Derivation: core constraint, invariant and counterexample | |
| Prediction before selected experiment | |
| Observed workspace/journal/budget states and evidence links | |
| Explanation of discrepancy | |
| Teach-back: why intent, effect, receipt and acceptance differ | |
| Transfer: remote create loses response; safe recovery and required evidence | |
| Transfer: verifier passed, then head changed; can old receipt publish review? | |
| Assistance/answer exposure and independent reassessment variant/outcome | |
| Later retrieval: pending / actual interval and evidence | |
| Unanswered question / next step | |

**Status:** all human fields intentionally empty; no mastery assessment inferred from this packet or AI implementation. Continue H0 with the four-owner map and one selected defect, then record genuine human evidence in `study/sessions/`. The [mastery tracker](../../docs/05-mastery-tracker.md) remains the human evidence authority. Affected source line anchors were refreshed against the current declarations on 2026-10-11. The [current readiness plan](../../research/system-readiness-plan-2026-10-11.md) and [verification record](../../research/system-readiness-verification-2026-10-11.json) own current engineering evidence; the [October9 review](../../research/production-code-review-2026-10-09.md) remains historical.

**VI:** Khi em tự giải thích được một trace và xử lý case đổi remote tool/head revision, mới có evidence transfer. Một buổi đọc code không tự hoàn tất H0–H15. Người học chọn next question từ chỗ chưa hiểu, không phải từ số file AI đã tạo.

The latest [qualification reading trace](../../docs/06-reference-code-reading-guide.md#provider-qualification-manifest-receipt-and-authority) supplies another H0 counterexample: a genuine transcript can still be mislabeled unless the original durable contract binds the manifest. Study it after the existing owner/Unknown trace; Huy's prediction and transfer fields above stay empty. [Installed rc4 evidence](../../research/provider-qualification-verification-2026-10-11.json) is engineering evidence only.
