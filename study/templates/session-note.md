# Production trace note

One note per trace, saved as `study/sessions/YYYY-MM-DD-trace-topic.md`, with one summary row in the [trace log](../../docs/05-mastery-tracker.md). Fields that do not apply can be deleted. See [D046](../../context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates).

```text
Date / author / time spent:
Starting artifact (run ID, request ID, commit, log or file path, upstream repository and revision):
What I expected before looking, and what would have proved me wrong (if written beforehand):
What actually happened (quoted from the artifact, not paraphrased):
Surprise or question:
Trace down, one line per layer (layer / source link / concrete values / observed or inferred):
Where I stopped, and why that layer was enough:
First principle reached (law or limit / chosen policy / measured assumption):
What I can now predict or change (Huy's words):
Proof (a later run, test or fix where the prediction came true):
Output (fix and regression test / write-up / upstream issue or PR / experiment idea):
Anything not yet solved anywhere, as far as I found:
AI help used (labeled):
Concepts touched (H-index, C1–C6):
Next trace:
```

**VI:** Chỉ ghi lời và việc em thật sự làm vào các ô của em. Phần AI giúp thì ghi riêng. Ô nào chưa có thì để trống; template không có nghĩa là đã làm.

For a milestone design review, append the fields below to the same note. Reference the canonical contract instead of copying a second specification. Leave the reviewer's decision blank until the review actually happens.

```text
Design scope / canonical contract revision:
Typed input/output identities and state owners:
Normal sequence / failure sequence:
Resource and deadline assumptions with units:
Rejected alternative and reason:
Counterexample / planned oracle and pass condition:
Blocking configuration decisions CFG-01–CFG-08:
Reviewer identity / AI assistance attribution:
Findings: unresolved / addressed / accepted within stated scope:
Design disposition and evidence:
Future implementation / research / operational evidence still required:
```
