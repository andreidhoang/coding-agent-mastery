# H0 before the first live call: predictions

**Status:** prepared. **Author of preparation:** AI, 2026-10-14. **Human evidence:** not yet recorded. Route stage S0 of the [build-ordered route](../../docs/02-mastery-learning-plan.md#build-ordered-route-2026-10-14).

Answer in writing **before** the first G1 call, and before opening the code, the [budget trace](../../docs/06-reference-code-reading-guide.md#exact-budgeteffect-trace-limit-100-claim-40-dispatch-bound-12-actual-9), the [expected-outcome table](../../hackathon/03-foundations-and-evaluation.md#discriminating-controls-and-predictions), or the S1 trace in the route (docs/02 and the 2026-10-14 chat diagram), which reveals the order of storage, charging and admission. If you have already read the answer to a prompt, mark it as practice, or record a `cue` when you saw only that order; independent evidence then needs a fresh variant.

**VI:** Viết câu trả lời trước khi chạy và trước khi mở code. Đoán sai vẫn là bằng chứng tốt, miễn là viết trước. Nếu đã đọc đáp án của câu nào, ghi câu đó là "luyện tập" và ta sẽ đổi sang biến thể mới để kiểm tra.

## Prompts

1. **Request contents.** List what the first Nebius request will contain. Which parts must stay byte-identical in the next turn's request, and what breaks if one changes?
2. **Truncation.** The response has valid usage, a complete-looking edit call and `finish_reason: "length"`. Predict the workspace bytes, spent versus reserved money, how many HTTP requests are sent, and the run's final status. What observation would falsify your prediction?
3. **Wrong model.** The response is complete, but its `model` field names a different model than the frozen one. Predict the same four quantities, and explain why.
4. **Lost reply, practice only.** Limit 100, claim 40, dispatch bound 12; the connection drops after the request is sent. Predict allowance, reserved, spent, and whether anything is resent. Our chat of 2026-10-13 already walked through this case, so it cannot count as independent evidence.
5. **Transfer.** Replace the code edit with a remote "create issue" tool whose reply is lost. What new evidence would make a retry safe?

## Evidence record

```text
Date / module / session / topic / minutes: 2026-10-14 / H0 with H2 and H4 previews / S0 / first live request: intent, effect, receipt, charge / 
Core concept and assessment scope: intent, effect, receipt, verification and acceptance are different facts; charge knowledge is separate from effect knowledge
Capstone component or milestone this will inform: G1 conformance; M1 baseline
Role capability C1–C6, when relevant: C1, C2
Design review D0–D7 and SYS/RT/EV/OP requirement IDs, when relevant: —
Purpose and user-visible consequence: know what the first paid call can and cannot do before paying for it
Prerequisites checked / gaps:
Invariant and assumptions:
Derivation / counterexample / units and limiting cases when relevant:
State/data owners and tiny diagram:
Permitted tools/references for this assessment: this note only; no code, docs/06 budget trace, hackathon/03 controls table or S1 route trace
Prediction BEFORE observation (author: Huy):
AI suggestion, if used (separately attributed):
What would falsify the prediction:
Sources and inspected code/revisions:
Experiment/config/artifact identity:
Environment / model / tool / grader versions when relevant:
Observed result (leave empty until observed):
Why prediction and observation agree or differ:
Failure diagnosis / repair / independent check / alternative ruled out:
Teach-back in my own words:
VI intuition / misconception corrected:
Transfer question and my answer:
Assistance and answer exposure (none / cue / partial trace / worked example): prompt 4 exposed in chat on 2026-10-13
Independent reassessment: fresh variant / Huy's reasoning / outcome:
Delayed retrieval: pending or actual later session / interval / outcome / evidence: pending
Learning gate status, demonstrated scope and remaining evidence: not demonstrated
Implementation status (separate): G1 waits for catalog, model ID and rates
Open questions and next learning step:
```

**VI:** Các ô trống là chỗ của em. AI không điền dự đoán, quan sát hay teach-back thay em, và tracker chỉ đổi khi có bằng chứng thật.
