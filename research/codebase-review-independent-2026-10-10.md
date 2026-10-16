# Independent review of bounded codebase repairs — 2026-10-10

**Final verdict: accepted for the frozen bounded repair scope; no unresolved must-fix source finding.** This is AI review evidence, not human mastery. The reviewer may write only this report and `runs/codebase-review-2026-10-10/independent/`; no implementation source was changed by the reviewer.

Read AGENTS, current state, H0 reference-runtime packet, the frozen refactor specification and its scope clarifications, and all three before-state audit reports. Compared changed implementation against `runs/codebase-review-2026-10-10/source-before`. Examined the new adversarial controls, protocol linkage, billing envelope, receipt/replay paths, and affected historical tests. The complete suite and real Docker integration belong to the coordinator.

**VI:** Review độc lập kiểm invariant và counterexample trên code đã sửa. Tests mock chỉ chứng minh nhánh logic được thử; không biến thành evidence model thật, GPU, production hoặc mastery của Huy.

## Findings

- **A1–A3 accepted on inspected source:** supported fixture admission checks requirements/grader/base/environment/model before graph and dispatch. Actual verifier identities and strict boolean verdict gate the receipt; confirmed cleanup and raw verifier observation survive rejected identity. CPU pass/fail/unsupported outcomes now identify the actual grader/environment. Completed historical review reads precede registry validation. Timestamp representation errors become ValueError. Failed-task recovery preserves quarantine/Unknown/retained-resource precedence and cannot advise reacquisition after obligations end.
- **X1, X2, X4 accepted on inspected source:** complete launcher evidence gates binding, provisioning, inventory and removal acknowledgement; successful authoritative absence can retire an owned instance even after failed removal. Redirect policy is enforced per credential-bearing request. Both protocols validate the entire proposed batch before the broker, including scripted history and final-turn/finish cases. Temporary result placeholders are not persisted.
- **R1–R3 accepted on inspected source:** nonblank string identity checks reject empty and container-valued acceptance claims without hiding assigned rows/spend. All supplied event facts must precede their recording timestamp, even in a late revision. Static admission rejects nonregular files before opening candidate source while keeping ordinary candidates unverified/pending.
- **X3 price-binding correction found, authorized and resolved:** the first implementation correctly rejected missing/wrong model proposals, but settled valid counters at the requested model's rates before model identity validation. `ProviderEnvelope.charge` does not establish a different model's applicable price. This is a concrete unsupported attribution in local mocked billing records, not a measured real-provider undercharge. The coordinator froze an addendum requiring both live protocols to retain raw/counters and known received effect, keep monetary liability unresolved on missing/wrong model identity, reject all proposals and avoid replay requests. Correct-model malformed semantic content must continue settling trustworthy usage. Resolved by the final follow-up: live response-model validation now precedes usage pricing on fresh and replayed receipts, after exact raw persistence. Final tests below passed; no historical settled record is rewritten.

**VI:** Số token và giá áp dụng là hai điều kiện khác nhau. Nếu request chọn model A nhưng response ghi B, không thể lấy giá A để tuyên bố đã biết bill. Giữ raw và reservation cho reconciliation; không xóa evidence hoặc gọi lại model để thử sửa lịch sử.

## Independent measurements

1. All three new regression files plus the existing native duplicate-history regression: **225 passed in 9.65s**, zero skipped, before the X3 billing follow-up. Log: `independent/scoped-pytest.txt`.
2. Eleven reviewer-authored controls: **11 passed in 0.29s**. They additionally reject false/float/string exit-zero values; require owned cleanup after incomplete candidate-launcher completion; retain a normally exited nonzero candidate result; and prove malformed usage plus wrong model preserves exact raw, `liability_unknown`, no extra request, no checkpoint and no tool effect across replay. Log: `independent/counterexamples-pytest.txt`.
3. The initial reviewer test used the incorrect expected enum `unknown` rather than the existing `liability_unknown`; three assertions failed for that authoring error. Corrected the reviewer test only and retained the first log as `counterexamples-initial-author-error.txt`. No product defect was inferred from those three failures.

All measured execution used temporary SQLite/artifacts/workspaces, CPU processes and HTTPX MockTransport. Docker observations in these reviewer controls are mocked. No full suite, real Docker daemon, PostgreSQL/Temporal backend, paid/live inference, GPU, cloud deployment or source publication was run by this reviewer. The initial scope scan shows no storage/schema, workload manifest/oracle/baseline or preserved reference/archive edits. No new production capability or automatic active-case recovery is established.

4. Final billing follow-up and adjacent protocol/diagnostic tests: **231 passed in 5.63s**, zero skipped. Command: `.venv/bin/python -m pytest -q tests/test_codebase_execution.py tests/test_live_harness.py tests/test_nebius_provider.py tests/test_nebius_http_errors.py runs/codebase-review-2026-10-10/independent/test_independent.py -p no:cacheprovider`. Log: `independent/final-billing-pytest.txt`. This includes the original eleven reviewer controls plus four new cases (both live protocols × missing/wrong model) showing that later explicit trusted bill settlement still cannot authorize completion on replay. The received raw artifact remains immutable and exactly one provider request occurs. Correct-model malformed semantics retain existing settlement tests.

These selections overlap and must not be added into a unique-test total. The first 225-test result predates the billing correction; final billing-dependent modules were retested in the 231-test selection. The unchanged authority/research sources retain their first selection evidence. Full-suite, lint and actual Docker results must come from the coordinator's separate final record, not from this review.

**VI:** Các con số là từng lần kiểm có overlap. Không cộng chúng thành tổng coverage, và không gắn kết quả source cũ sang source mới. Bốn case bổ sung tách rõ quyền settlement với quyền chấp nhận completion.

## Exact final source and compatibility

Final reviewed SHA-256 identities are recorded in [final-reviewed-hashes.json — local-only](../docs/github-snapshot.md#omitted-local-evidence), captured at 2026-10-10T08:20:30.106381+00:00. Implementation declaration anchors inspected on that source: [fixture admission](../service/engine.py#L57), [returned identities](../service/engine.py#L225), [timestamp](../service/contracts.py#L82), [recovery guidance](../service/recovery.py#L7), [launcher completion](../service/execution.py#L248), [billing identity](../service/harness.py#L18), [whole-batch validation](../service/harness.py#L322), [response parsing](../service/providers.py#L61), [redirect boundary](../service/providers.py#L142), [acceptance identities](../evals/analysis.py#L38), [chronology](../evals/analysis.py#L112), and [static entry classification](../workloads/registry.py#L199).

The optional Anthropic expected-model argument preserves offline parser compatibility. Model identity is strict on live adapter/harness paths; mocks now state their intended model. Correct-model malformed semantics still preserve trustworthy accounting independently of tool admission. RuntimeStore schema 2, ledger implementation, protocol data representation, asset lock and synthetic workload population are unchanged. Historical already-settled pricing evidence is retained for operator reconciliation, not retrospectively repaired by this patch. Future provider aliases need an explicit contract; no alias behavior is assumed here.

No residual must-fix finding was established in this bounded review. The acknowledged gaps—live-provider rates/conformance and quality, GPU execution, active-case process-loss recovery, hostile concurrent host mutation and operated production readiness—remain outside the demonstrated result.


| Final implementation | SHA-256 |
|---|---|
| `evals/analysis.py` | `028e399b9113b5dd9b04570673a5eaa6b047effbf8a1f60347eaa34bb7efd323` |
| `service/contracts.py` | `e27bd144b3600bf7d653fb90f6c052b749e406d68a005dcf32ef6e8a9500f19c` |
| `service/engine.py` | `0df2d0e658f10efd5d5bcd7122d354443aaeb7c21d92d7f59aa53cb410c14e2c` |
| `service/execution.py` | `47ce32c3d9c1cb1e739c34adfac58b21b02a4b6bfcc1c0e8307f33d3929fb4b6` |
| `service/harness.py` | `c3f48b9bb332a958c3c3d878ab7c7a91e2573567659d3c34e277b77c9445e4f7` |
| `service/providers.py` | `ceed1b520d954d93bff191cb3b05cd30d4f35035ec59c51a11dc0bcbb302ff78` |
| `service/recovery.py` | `1db8453963bcf7aaddcb958eca3e6da806fc3fc7ca8850c65b8c708d626eb6f2` |
| `service/verification.py` | `a6076e4a8ba52aeabe519a7339ca2a7a8afce0eee76878fac46922fd473e6f8b` |
| `workloads/registry.py` | `3e1ca8a0885725979fa3c389966347eaca6dba0c910b43d9b8f524f66201ef68` |
