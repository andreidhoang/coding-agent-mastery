# E6 repair evidence implementation

2026-10-10. AI-authored reference implementation, scoped to `service/repair_reporting.py` and its focused tests. The root integration owns the repair runner and CLI. This record does not establish human mastery, actual NVIDIA model capability, live inference, paid hosting or a submitted hackathon entry.

## Engineering contract

Purpose: give a maintainer an offline issue → committed progress → stored diff → independent test summary → costs and retained reservations → downloadable evidence flow. The runtime owns task and verification authority; the reporter derives a detached view and cannot create a verification or review receipt. `write_repair_report(output, snapshot, events, *, artifacts=None)` returns a JSON-detached dictionary with top-level `verified` and writes `repair.html`, `repair.json`, `change.patch`, plus the existing reporter's `snapshot.json`, `trace.json`, and `trace.html`. The repair-derived trace HTML's fixed fixture caption is relabeled with the actual evidence label; the existing reporter source and fixture behavior stay unchanged.

The input is the API-visible snapshot. The reporter reads no controller database, supervisor input store, provider configuration file, or private recipe. It follows only the selected verification's explicitly scoped public `evidence_ref` through the supplied artifact store. Private assertions and raw outputs are absent from the rendered case projection; the final verifier already produces redacted public evidence.

Invariants:

- A verification claim requires the selected current head's reconstructed text-tree identity and the latest matching trusted receipt's candidate, tree, grader, environment, contract, generation, tenant and task identities. A stale pass, worker test, missing head, or conflicting available artifact cannot produce `verified=True`. Equal recorded timestamps favor a non-pass result.
- Terminal `fail_execution` increments task generation to revoke authority. A failed task may display its preceding generation's fail/error receipt only when `failure.generation + 1 == task.generation` and the receipt's generation and evidence reference exactly match the committed failure transition. Historical pass receipts never restore verification in failed state.
- A missing public artifact is reported as unavailable; the committed receipt identity/outcome remains visible separately from unavailable case details. The report does not manufacture assertions or test counts from absent artifacts.
- `change.patch` contains exactly the selected stored UTF-8 patch bytes, including existing line endings. With no head, a stored worker candidate is explicitly candidate-only and unverified. With no valid candidate patch, the file is empty and the download is labeled unavailable. Diff reconstruction is an integration-level gate owned by the root, not an inferred reporter measurement.
- Worker-test requests are counted cumulatively from all `run_tests` dispatches, including prior attempts. Successful tool transport is not labeled a passing test. Settled spend, total reserved, Unknown effects, Unknown reserved bounds and remaining reservations are separate figures; no currency conversion or double addition is inferred.
- Every displayed variable string is HTML-escaped; embedded JSON escapes HTML delimiters and JavaScript line separators. There is no executable JavaScript, remote stylesheet, remote asset, fetch, or provider call in `repair.html`. All download destinations are fixed relative filenames.
- Evidence explicitly distinguishes native mock transport, operator configuration and unspecified runtime evidence. Human review remains a separate state even when independent checks pass.

References inspected: [execution specification](../../hackathon/04-execution-specification.md), [existing report writer](../../service/reporting.py), [current-head authority](../../service/storage.py), [candidate manifest](../../service/integration.py), [supported repair runner](../../service/repair.py), [redacted verifier](../../service/repair_verification.py).

## Distinguishing checks and measured results

`uv run pytest -q tests/test_repair_reporting.py`: **24 passed** after the integrated-review repair. `uv run ruff check service/repair_reporting.py tests/test_repair_reporting.py`: **clean**. These are focused reporter checks; integration and independent source review are separately owned by the root.

Checks cover exact UTF-8/CRLF patch download bytes, JSON/report equality, detached input/output ownership, nine stale identity variations, altered current tree bytes, failed/current receipts, no head, no candidate, unavailable artifacts, conflicting public evidence, cumulative worker requests, reserved Unknown accounting, explicit evidence labels, and hostile `</script><script src=...><img onerror=...>` text in issue/patch/progress. HTML parsing confirms only an inert JSON script element, no attacker-created image, no event handler or external source attributes, and local-only download links.

Independent integrated review found that the first reporter version filtered only the task's current generation, hiding actual final fail/error receipts after `fail_execution` revocation. The repair adds faithful generation-2 task / generation-1 failure tests for both outcomes, denies historical passes and unbound historical failures, and tests the operator-configured trace caption. These are regression checks against inspected `RuntimeStore.fail_execution` semantics, not an invented claim that the reporter ran a live provider.

Failure modes remain explicit: a report cannot supply absent public evidence, reconstruct a missing candidate, or promote a stale verifier result. A receipt records the configured bounded recipe/environment only. Opening the HTML is read-only; changing a report file is not a state transition in the runtime.

**VI:** Report chỉ đọc snapshot công khai và receipt đã commit. `verified` nghĩa là identity của current head khớp receipt độc lập; review của người vẫn pending. Khi fail, task tăng generation để revoke authority; chỉ receipt fail/error được bind bằng generation và evidence_ref của failure mới được hiển thị, còn pass cũ không thể thành verified. Nếu artifact không còn, phần case ghi unavailable, không tự bịa kết quả. Worker test count lấy từ toàn bộ dispatch nên restart không làm reset count. Patch tải xuống giữ nguyên bytes đã lưu; mock transport và mastery của Huy vẫn là hai loại evidence riêng.
