# Lab verification record

Verified locally on 2026-10-08. AI-written educational code; trusted fixture only.

- `python3 -m unittest -v test_harness.py`: **15 tests passed** after independent review and fixes.
- `python3 harness.py`: baseline assertion failure, then a real fixture edit and successful verification; **4 scripted model replies, 3 durable tool results**.
- Recorded run: [summary — local-only](../docs/github-snapshot.md#omitted-local-evidence), [events — local-only](../docs/github-snapshot.md#omitted-local-evidence), [final fixture — local-only](../docs/github-snapshot.md#omitted-local-evidence).
- Ideal arithmetic check: 16,850,000 cumulative uncached input tokens; 317,000 unique growing-prefix tokens; 16,533,000 reused input tokens under the stated model. No timing, cache-hit or cost benchmark was inferred from this arithmetic.

Independent review reproduced two defects in the first implementation: a stale cached passing result could certify changed bytes; and a clean process exit could bypass the assertions. The revised implementation binds the result to the fixture digest and requires a normal-completion marker. Both regression tests passed. The marker is not an adversarial security boundary.

**VI:** Đây là evidence của một phạm vi hẹp: contract của lab và fixture đã chạy. Chưa có measurement về model thật, API streaming, sandbox, GPU serving, cloud reliability hoặc training. Cũng chưa có evidence rằng Huy đã qua mastery gate.
