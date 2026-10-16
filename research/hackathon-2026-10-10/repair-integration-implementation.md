# Repair integration test implementation — 2026-10-10

The supported repair flow now has integration coverage in [tests/test_repair.py](../../tests/test_repair.py). The tests exercise the actual frozen repository, Python function recipe/controller, provider approval, native Nebius Chat Completions adapter, harness, RuntimeStore, artifact store and RepairEngine. Only candidate execution and provider HTTP are injected in the default path. The implementation contract remains [hackathon/04-execution-specification.md](../../hackathon/04-execution-specification.md).

## Ownership and invariants

The authority database owns attempts, dispatches, request exposure, auxiliary test reservations, candidates, final verification and review eligibility. Public evidence uses one LocalArtifacts root; frozen source/recipe/provider input uses a separate private root. The model sees the issue, public interface, public cases, source and tool feedback. The supervisor owns private assertions. The test factory sees only per-case RPC inputs and candidate bytes, never expected answers from the recipe.

`LiteralSandboxFactory` is a bounded fixture truth table for the owned `normalize_slug` demonstration. It selects literal outputs using the fixture's exact input cases and known source markers. It does not import, evaluate or execute candidate Python in the host process. This mock establishes controller mechanics and state transitions, not semantic execution of arbitrary candidate code. A separate opt-in test uses the actual Docker verifier with native mock HTTP when `CAM_TEST_SANDBOX_IMAGE` identifies an already present immutable image.

**VI:** Database giữ quyền chạy và chi phí; model không giữ private assertions. Mock trả literal values theo vài case cố định, nên kết quả default chỉ chứng minh cơ chế control plane. Test Docker opt-in mới chạy candidate Python thật trong container; không có bước chạy candidate trên host.

## Distinguishing tests

| Experiment | Observed assertion |
|---|---|
| Read → failing public tests → digest-guarded edit → passing public tests → finish → private final checks | The current source tree changes between worker test callbacks; final receipt binds that exact changed tree; review is pending and execution is review eligible |
| Public-only plausible candidate and unchanged completion | Private final checks fail and no review is published |
| Private ID/input/expected-output sentinels | Absent from native requests, public artifacts, status, snapshot and event API responses; the private input digest cannot download its bytes through the public artifact API |
| Sequential per-case environments and patch workspace cleanup | All confirmed physical slots have retirement evidence; injected cases never overlap; the worker patch grant is separate from auxiliary verifier reservations |
| Repeated completed invocation | No additional HTTP request, test instance, budget change or event frontier change |
| Clean pause after two turns → close/reopen → resume | Three remaining requests continue the exact retained native transcript, a fresh attempt increments the node epoch, and the previous owner is fenced |
| Cumulative max turns and worker-test allowance | Resume consumes the remaining turns; another public-test request gets a known limit error without provisioning another public-test container |
| Synthetic positive cost envelope | Settled charges survive reopen; request admission rejects a bound larger than the remaining task budget before HTTP |
| HTTP timeout after a prior checkpoint | Unknown effect retains its request bound; resume makes no HTTP request and requires reconciliation |
| Complete response with invalid usage | Raw response is retained as a known effect, billing remains unsettled and its bound remains reserved; resume is refused |
| Resumed model/edit settles, then checkpoint write fails | An earlier attempt's checkpoint cannot rewind the later attempt's effects; another resume does not claim, dispatch or rerun tests |
| Final pass receipt commits, then review publication fails | Resume reuses the immutable final receipt and publishes pending review without another provider or verifier call |
| Final fail receipt commits, then terminal-state write fails | Resume reuses the failed receipt, records failure and does not repeat final checks |
| Uncertain test cleanup | The verifier auxiliary slot remains retained, the test dispatch is Unknown, no next case starts, and resume is refused |
| Model/bound/environment/private-input drift | Rejected before an attempt, provider dispatch or candidate execution |
| Unknown, missing, invalid or unbounded repair-spec fields | Rejected by both contract validation and authority submission |

Native histories are compared byte-for-byte as parsed JSON objects, including opaque reasoning content and tool-call linkage. Assertions identify attempts/dispatches by their stable identities rather than assuming database list order is execution order.

The positive ledger envelope uses synthetic prices only: 1,000 micro-USD per million input/output tokens, request bound 34 micro-USD and a rounded 1 micro-USD charge for each mock 10-input/10-output response. This is deliberate test data, not an observed or approved live provider price.

## Focused validation

Measured on the working tree on 2026-10-10:

```text
.venv/bin/python -m pytest tests/test_repair.py -q
30 passed, 1 skipped, 1 warning in 3.54s
.venv/bin/ruff check tests/test_repair.py
All checks passed!
```

The skipped test requires an explicit already present immutable Docker image through `CAM_TEST_SANDBOX_IMAGE`. The warning comes from the installed Starlette/FastAPI TestClient HTTPX compatibility path. No live provider request, new image pull or paid execution was made by these tests. Full-suite and real Docker integration results must be recorded separately by the integrated verification owner; this focused result does not inherit prior backend measurements.

Root-owned repairs to cross-attempt checkpoint frontier checks, unsettled-billing refusal and immutable final-receipt reuse passed the added crash regressions. The tests changed no source implementation. One development failure was an incorrect test assumption about list ordering; the assertion now compares original/resumed attempt identities. Another initial budget experiment assumed settled actual charges refill an attempt allowance; the corrected experiment tests remaining task admission after clean retirement/reclaim.

**VI:** Evidence hiện tại là 30 test integration local pass, một Docker test chưa chạy ở lượt này. Không suy ra capability của NVIDIA model, readiness vận hành production hay human mastery. Hai lỗi khi viết test là giả định thứ tự list và allowance tự refill; đã sửa test theo contract thực tế, không đổi authority semantics để làm test pass.
