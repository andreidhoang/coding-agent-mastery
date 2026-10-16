# H0 learning packet: intent, effects and verification

**Status:** optional background lesson since [D046](../../context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates); there are no gates. **Suggested duration:** 60–90 minutes. **Prerequisites:** basic Python functions/exceptions, file reads/writes and the meaning of a test assertion. Use a short remedial explanation when needed.

**VI:** Buổi này học boundary trước framework. Điều cần hiểu là một hành động có thể xảy ra ở filesystem mà journal chưa biết; và model có thể nói xong dù không có bằng chứng đúng.

Role connection: this session begins C1/C2 in the [Multi-Agent Scaling capability map](../../capstone/06-target-role-and-research-contract.md). Honest effect/receipt/verification state is a prerequisite for trustworthy scaling measurements. This does not change the current lesson or its learning gate.

## 1. Purpose and whole-system position

The capstone must return a correct change and survive failures. Begin by locating four objects: durable events/action intent, model-visible context, environment bytes/processes, and verification evidence for a particular artifact. These objects can disagree temporarily; the system needs an honest recovery/finish decision. Read only sections 1–3 of [the first-principles chapter](../../docs/01-first-principles-and-system-map.md) initially.

**VI:** Journal giống sổ theo dõi công việc; filesystem là đồ vật thật đã bị thay đổi; prompt là phần thông tin đưa cho người quyết định; verifier là phép đo trên một phiên bản cụ thể. Không có một bản copy nào tự thay thế được cả bốn.

## 2. Tiny case and prediction before observation

Consider one action: edit a trusted file to replace subtraction with addition. The controller records intent, the tool changes bytes, and the controller records a result. Separately, a verifier checks those bytes. Draw four lanes: journal, model context, workspace and verifier. Mark the boundaries in this sequence:

```text
intent committed → file effect → result committed → verification → delivery
```

In the [prepared note](../sessions/2026-10-08-H0-preparation.md), record your predictions **before reading the relevant test body, running it, or opening its saved result**:

1. The process dies after the file effect but before result commit. What does the file contain, what can the journal prove, and what should retry do?
2. The model says “done” before verification. What evidence, if any, supports a verified finish?
3. Verification passes, then someone changes the file. Can the old result establish correctness of the new bytes?

Include an observation that would make you revise each answer. Predictions need not be correct. AI suggestions must be attributed separately.

**VI:** Dự đoán phải nói rõ từng nơi biết gì. “Task fail” là quá chung: file có thể đã sửa đúng, nhưng hệ thống chưa đủ bằng chứng để repeat hoặc giao kết quả.

## 3. Read the implementation after predicting

| Mechanism | Inspected code | Distinguishing test |
|---|---|---|
| Intent/result journal and unfinished actions | [Ledger](../../lab/harness.py#L35), [begin](../../lab/harness.py#L63), [finish](../../lab/harness.py#L78) | [Crash after effect](../../lab/test_harness.py#L82) |
| Final response versus verified finish | [Loop](../../lab/harness.py#L198) | [Claimed completion](../../lab/test_harness.py#L93) |
| Evidence tied to current bytes | [Digest comparison](../../lab/harness.py#L209) | [Stale verification](../../lab/test_harness.py#L106) |

Trace one call ID, its arguments, file digest and receipt through the code. Explain which operations share a database transaction and which do not. The lab is single-owner, trusted-fixture code; it does not resume the full model conversation or sandbox hostile code.

**VI:** Quan sát syntax chỉ là bước đầu. Hãy nối mỗi block tới lỗi nó ngăn chặn: identity để tránh lặp nhầm, transaction để gắn result với event, digest để tránh dùng bằng chứng của file cũ.

## 4. Small experiment after the prediction

The following tests use disposable fixtures. Run only these focused cases after recording the predictions. The folder setup itself has not run them or filled your observations.

```sh
cd lab  # from the repository root
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  test_harness.HarnessTests.test_crash_after_effect_is_unknown_and_never_replayed \
  test_harness.HarnessTests.test_asserting_done_does_not_mean_verified \
  test_harness.HarnessTests.test_replayed_test_cannot_verify_a_different_revision
```

Use [the lab guide](../../lab/README.md) for the wider walkthrough after prediction. Record observed outcomes and explain discrepancies. A passing contract test is evidence about this lab mechanism, not production readiness.

**VI:** Experiment nhỏ tách noise model khỏi lỗi hệ thống. Đừng chỉ ghi “3 tests pass”; cần nói mỗi phép thử quan sát điều gì và điều đó có bác bỏ dự đoán ban đầu không.

## 5. Teach-back and transfer (optional)

Explain in your own words: why intent is not proof of an effect; why an effect without a receipt differs from a known failure; and why verification must identify the artifact it tested. Draw the trace from memory, then compare it with the source.

Transfer case: replace the file edit with a remote API that creates an issue, and lose its response. Explain what additional identity/receipt lookup would be needed before retrying. Do not implement this remote tool yet. Connect the reasoning to the future [runtime recovery contract](../../capstone/02-runtime-contracts-and-recovery.md) only after explaining the tiny case.

Mark this session's gate demonstrated only when your note contains a prediction, observed evidence, causal explanation and transfer answer. This first session does not complete every H0 requirement. Next: H0's second session traces model/tool envelopes and evidence ownership; prepare that packet when this session reveals the remaining questions.

**VI:** Bài transfer là cách phân biệt hiểu cơ chế với nhớ test. Nếu đổi filesystem thành API mà lời giải chỉ còn “retry”, ta cần học thêm về uncertain effects trước khi build recovery.
