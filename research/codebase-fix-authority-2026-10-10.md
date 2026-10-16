# Authority, ingress and recovery repairs — 2026-10-10

AI-authored bounded implementation of A1–A3 from [the frozen specification](codebase-refactor-spec-2026-10-10.md) and [authority audit](codebase-audit-2026-10-10-authority.md). The coordinator froze two narrow additions before the edits: complete CPU verifier identity metadata, and application of X1's shared acknowledged-process predicate to the Linux verifier's image preflight. No RuntimeStore schema, transition, lock or API route changed. Human mastery remains pending.

## Ownership and implemented contracts

- **A1 admission:** [ReferenceEngine preflight](../service/engine.py#L61) binds the supported model/repository to registered ordered requirements, actual locked grader, baseline tree and configured environment before graph/resource/worker effects. An unknown fixture also becomes an explicit ValueError. The terminal replay branch precedes registry validation, preserving receipt-only inspection after registry or environment drift.
- **A1 receipt:** [returned observation checks](../service/engine.py#L220) preserve raw verifier evidence and already confirmed physical retirement, then require a strict boolean verdict and exact returned tree/grader/environment identities before recording verification. Receipt fields use the validated returned values. Rejected observations create no verification or review eligibility; the controller raises ValueError for the mismatch rather than manufacturing a failed grader receipt.
- **A1 CPU producer:** [FixtureVerifier](../service/verification.py#L84) includes tree, grader and environment identities on correct, incorrect/baseline, and unsupported arbitrary-candidate results. Identity follows a checked frozen asset registry; arbitrary source remains unexecuted by the CPU backend.
- **A2 ingress:** [timestamp conversion](../service/contracts.py#L82) normalizes oversized numeric conversion and platform date conversion overflow/OSError into ValueError. Strict type, finite and nonnegative checks remain; booleans remain invalid. Numeric finite values such as `1e308` retain their existing accepted representation. Both HTTP deadline fields now produce structured 422 `invalid_input` with all task/event/outbox table counts unchanged.
- **A3 recovery:** [terminal classification](../service/recovery.py#L19) includes failed tasks. Quarantine, unresolved effects and retained physical resources retain their original precedence, followed by settlement/inspection-only terminal guidance. This helper grants no authority.
- **X1 shared seam:** [Linux image preflight](../service/verification.py#L127) uses the execution lane's `_acknowledged_process_result`; timeout with exit zero cannot establish image identity. A complete normally exited observation with retired process group remains valid. This is a mocked image-inspection check; no Docker process ran in this lane.

**VI:** Contract nói cần kiểm gì, verifier nói chính bytes nào đã được kiểm. Engine chỉ nối hai object sau khi identity trùng và verdict là boolean thật. Nếu verifier trả sai grader, ta vẫn giữ artifact quan sát và cleanup đã xác nhận, nhưng không tạo receipt nói candidate đã pass. Failed task vẫn giữ nghĩa terminal; unknown effect và resource chưa retire phải được đối soát trước.

## Distinguishing experiments and measured checks

Prediction before editing: altered requirements/grader and returned identities would pass or reach attribution in the original engine; oversized deadlines would escape as arithmetic errors/HTTP500; failed recovery would recommend reacquisition. Negative controls should fail before repair and pass afterward, while valid fixtures preserve review-eligible/pending and resume without new worker attempts.

[The final 56-case regression file](../tests/test_codebase_authority.py) exercises independently changed requirements, order, grader, base, environment, model/repository and unknown registry selection; true and false outcomes with wrong/missing receipt fields; string/integer/container/null verdicts; complete CPU pass/fail/unsupported metadata; confirmed mocked Linux retirement despite identity rejection; valid failed receipts; registry/environment-drift terminal reads; finite timestamp boundaries, boolean/nonfinite/oversized numeric and platform conversion failure; both HTTP deadline fields with table-count immutability; and failed recovery with no obligations, retained resources, unknown effects and quarantine.

The first in-place pre-edit run of the then-54-case selection observed **38 failed, 16 passed**. To bind the final test file to the preserved baseline after adding positive image-preflight and unknown-fixture cases, a disposable copy used preserved `source-before/service` and `source-before/workloads` Python sources plus unchanged workload data checked against `before.json`. The final before-source run observed **39 failed, 17 passed in 8.79s**. All 39 failures are expected contract regressions; the positive controls remain passing. Preserved source and historical runs were not edited. One preliminary copy omitted workload JSON assets and produced setup failures; that invalid harness run is retained as `before-tests-missing-assets.txt` and is excluded from defect counts.

Final current-source selection:

```sh
.venv/bin/python -m pytest -q tests/test_codebase_authority.py tests/test_engine.py tests/test_api.py tests/test_audit_authority.py tests/test_verification.py -p no:cacheprovider
.venv/bin/ruff check service/engine.py service/contracts.py service/recovery.py service/verification.py tests/test_codebase_authority.py
```

**Observed: 88 passed, 2 skipped in 9.11s; Ruff passed.** The 56 new cases are included in 88, not additional. Existing 1/2/4-worker fixture runs and saved-head resume pass. Both skips require an explicitly selected Linux sandbox image. [Machine-readable result and hashes — local-only](../docs/github-snapshot.md#omitted-local-evidence), [before log — local-only](../docs/github-snapshot.md#omitted-local-evidence), [after log — local-only](../docs/github-snapshot.md#omitted-local-evidence), and [lint log — local-only](../docs/github-snapshot.md#omitted-local-evidence) retain the evidence.

**VI:** 39 case đỏ ở source cũ và xanh ở source mới chứng minh tests phân biệt boundary đã sửa. 88 là focused selection gồm case mới và controls cũ; không cộng nó vào full-suite count của agent khác. Platform timestamp overflow được mô phỏng để kiểm exception classification, không phải đo mọi OS.

## Source identities at focused verification

| File | SHA-256 |
|---|---|
| `service/engine.py` | `0df2d0e658f10efd5d5bcd7122d354443aaeb7c21d92d7f59aa53cb410c14e2c` |
| `service/contracts.py` | `e27bd144b3600bf7d653fb90f6c052b749e406d68a005dcf32ef6e8a9500f19c` |
| `service/recovery.py` | `1db8453963bcf7aaddcb958eca3e6da806fc3fc7ca8850c65b8c708d626eb6f2` |
| `service/verification.py` | `a6076e4a8ba52aeabe519a7339ca2a7a8afce0eee76878fac46922fd473e6f8b` |
| `tests/test_codebase_authority.py` | `344806e1cfed8179ac835f891958f904fc1a47044fd13f6df07d70bfd106f506` |
| Shared execution dependency `service/execution.py` | `47ce32c3d9c1cb1e739c34adfac58b21b02a4b6bfcc1c0e8307f33d3929fb4b6` |

Execution source belongs to the independent execution lane; its hash identifies the dependency used in this focused check, not authority-lane authorship. Any later integrated edits need the coordinator's final verification record.

Limits: local CPU/SQLite fixtures and mocked Linux boundaries only. This lane did not run the full suite, real Docker/PostgreSQL/Temporal/S3 integration, paid inference, network calls, GPU execution or cloud deployment. Raw rejected verifier artifacts are retained by content address; they are not accepted task receipt evidence or a new API artifact-membership grant. General recovery automation, malicious-host isolation and production readiness remain outside the repairs. Next gate is independent integrated review and the coordinator's final checks; no human learning evidence was created.
