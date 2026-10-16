# Serving readiness audit, 2026-10-11

AI-authored, read-only source audit plus disposable local adversarial probes. Read `AGENTS.md`, `context/current-state.md`, the H0 reference-runtime packet, the implementation coverage register, service/ops/hackathon contracts and relevant runtime/tests. The recorded baseline is accepted skills disclosure step4 (1,820 tests/156 subtests reported in its own verification); skills recovery is a separate concurrent lane. This audit does not rerun or inherit that count and does not assess human mastery.

## Decision

The code is a substantial offline reference with transactionally owned tasks, budgets, receipts, verifier identity and provider evidence. It is not a configured operated production service. The immediate dependency-independent serving build is [the frozen configured-local-serving specification](serving-preflight-spec-2026-10-11.md): atomic opt-in pending-task caps, strict fixture composition root, an actual supervised runner, trustworthy readiness and real HTTP lifecycle tests. A generic pass/fail readiness manifest alone would not close the implementation gap.

**VI:** Các primitive có thể đúng trong test nhưng chưa tạo thành service có vòng đời. Cần nối API→queue→worker→receipt và đo cách từ chối/quay lại sau restart; không được dùng số test để thay bằng chứng vận hành.

## Concrete observations and priority

Line anchors below were inspected in the pre-change checkout on October11. Concurrent implementation may move them; source identities below fix this audit's baseline.

| Finding | Evidence | Classification / required action |
|---|---|---|
| New submissions have no accepted-work capacity bound | [submit](../service/storage.py#L415) checks admission switch/deadline then inserts task/start; physical caps are in [claim](../service/storage.py#L532) | Concrete gap against OP-01/02, blocking bounded external serving. Add atomic queue+running caps in existing owner |
| Requested limits can differ from effective persisted limits | [constructor](../service/storage.py#L131) inserts initial guard with conflict-do-nothing and reuses existing guard | Intended persistence, hazardous if bootstrap assumes new arguments changed policy. Validate effective state; no silent upgrade |
| `/health` is static informational liveness | [health](../service/api.py#L219) reports captured configured flag and `production_readiness:unmeasured` | Not a false production claim; insufficient as a readiness probe. Add dynamic independent readiness |
| No configured application bootstrap/runner lifecycle | [Dockerfile](../ops/Dockerfile#L63) starts unconfigured factory; [CLI](../service/cli.py#L11) has demo/doctor/repair commands | Source gap; default503 is correct, but no configured service is delivered by that image |
| Dispatcher requires trusted injected runner/cleanup | [LocalOutboxDispatcher](../service/workflows.py#L198), [Temporal relay](../service/workflows.py#L247) | Strong reusable seam. No new orchestration engine needed. Cleanup cannot be an acknowledgement-only callback |
| Fixture CLI submission regenerates absolute deadlines | [submit_fixture](../service/engine.py#L31) uses current time each call; [store retry](../service/storage.py#L423) requires exact original payload | HTTP composition must freeze contract before retries; blindly invoking helper on retry causes conflict |
| Clean restart differs from active process-loss recovery | [repair CLI](../service/repair_cli.py#L113), [execution contract](../hackathon/04-execution-specification.md#L50) | Physical-instance journal and interrupted-run reconciler remain real source gaps. Keep Unknown and reservations; do not replay |
| Existing ingress bounds bytes, not arrival duration/concurrency | [BoundedIngress](../service/api.py#L67) accumulates bounded chunks before routing | Deployment must impose connection/header/body-time/concurrency limits. Local-loopback slice does not establish internet overload resistance |

**VI:** Admission capacity, physical capacity và monetary exposure là ba trục riêng. Một task đã cancel có thể nhường chỗ nhận việc mới nhưng vẫn còn sandbox hoặc tiền chưa đối soát. Queue cap không được làm mất hai loại liability đó.

## Measured disposable controls

Executed with the repository `.venv` against a fresh temporary SQLite file and `LocalArtifacts`; the temporary directory was removed afterward. No live model, network service, GPU, Docker or historical store was used. The test created a minimal valid task contract and submitted distinct keys, then reopened the same disposable store and queried the ASGI health route after quarantine.

```json
{
  "queue_probe": {
    "configured_service_slots": 1,
    "configured_tenant_slots": 1,
    "submitted": 20,
    "states": ["queued"],
    "outbox_start_count": 20
  },
  "health_when_quarantined": {
    "configured": true,
    "mode": "reference_api",
    "production_readiness": "unmeasured"
  },
  "reopened_limits_probe": {
    "requested_service_slots": 0,
    "effective_service_slots": 1,
    "requested_tenant_slots": 0,
    "effective_tenant_slots": 1
  }
}
```

This is three observed mechanisms, not a sustained load study. It demonstrates why a new serving bootstrap must inspect actual state and why slot caps cannot be marketed as a queue bound. The health response is accurately labeled unmeasured; treating it as a production-ready signal would be the caller's error. The new readiness endpoint must avoid that ambiguity.

Existing boundary checks were also run: `tests/test_api.py`, `tests/test_audit_ops.py` and `tests/test_audit_api_artifacts.py`: **18 passed in 9.50s**, no skips. These checks cover the existing bounded/authenticated API, accepted artifact namespaces and owned-process timeout cleanup. They do not test the newly proposed serving implementation or add to the historical integrated suite count.

**VI:** Thử20 task là counterexample đủ để bác bỏ giả thuyết “slot1 nghĩa là chỉ nhận1 task”. Nó không đo throughput hay latency. Ta cần sửa invariant trước, rồi mới có ý nghĩa khi chạy load test.

## Existing controls worth preserving

Authentication derives tenant/reviewer/repository/profile authority from explicit server-held principals; no default secret exists ([API](../service/api.py#L137)). Strict JSON/body checks, repository rechecks and accepted-reference artifact authorization are already implemented. The store has immutable idempotent submissions, current incarnation/owner fencing, intent-before-effect records, separate effect/billing knowledge, physical retirement evidence, exact candidate/verification identity and explicit restore quarantine. Do not replace those owners with service-local state.

The Linux sandbox uses pinned local images, no host mounts, no network, non-root identity, read-only root, dropped capabilities, no-new-privileges and CPU/memory/PID/tmpfs/output limits ([DockerSandbox](../service/execution.py#L340)). Creation/removal bind nonce and immutable instance identity. This supports the bounded exercised local verifier profile; it does not establish hostile multi-tenant kernel containment or GPU isolation. The offline serving slice can reuse [FixtureVerifier](../service/verification.py#L73), which only executes exact authored locked controls and rejects arbitrary candidate bytes.

**VI:** “Có sandbox” chưa đủ thành một security claim chung. Ta phải nói code nào chạy ở đâu, credential có vào đó không, ai xác nhận process đã chết và workload tấn công nào đã thử. Fixture mode có threat model nhỏ hơn public upload.

## Remaining work by type

| Type | Required evidence or source work | Why a local green suite does not close it |
|---|---|---|
| Implementable offline now | Configured serving, atomic admission limits, worker lifecycle, dynamic readiness, pinned installed-package smoke | No hardware/provider dependency; specified immediate build |
| Implementable core follow-on | Physical-instance journal, safe interrupted-run reconciliation, queued expiry/fairness, retained-data lifecycle, explicit live repair API admission, deployment identity/secret/transport integration | These behaviors need contracts and code; declaring them “unmeasured” alone would hide missing implementation |
| Operational environment gates | Persisted PostgreSQL/Temporal/artifact deployment, backup restore and beyond-frontier reconciliation, old-writer fencing, restore RPO/RTO, cancellation/drain/rollback, sustained open-loop load and tenant fairness | Local adapter tests and simulated timings are narrower measurements |
| Live research gates | Authorized account/model/endpoint/rate conformance; supported unseen repair trials; all-assigned denominators; resource-matched agent comparisons; held-out confirmation | Scripted/native-mock correctness does not measure model coding quality |
| Hardware gates | GPU runtime/driver/isolation identity, numerical controls, cold/warm timing, memory/resources, timeout/reset/retirement, profiler and matched baseline | CPU reference and preflight cannot measure CUDA execution/performance |
| Hackathon release gates | Actual NVIDIA/Nebius use, public licensed source/test build, judge access, public video/feedback and deadline compliance under the existing hackathon packet | No account/publication/spend authorization is inferred here |
| Optional beyond selected product | General arbitrary-repository execution, full hosted multi-tenant scale, extra model routing/agent counts, general MCP/LSP, semantic compaction and new training stack | Useful only when their selected contract/experiment requires them; cannot distract from current mandatory repair/serving gates |

Packaging remains source-specific. The October10 offline candidate is a frozen historical artifact; October11 changes do not retroactively refresh its acceptance evidence. The current Dockerfile has a separate networked pinned-lock build recipe and intentionally no configured workers/credentials. Rebuild/test new source under a new identity while retaining prior artifacts. The local PostgreSQL Compose profile is explicitly tmpfs/trust/disposable, not a durable deployment.

## Current primary research and engineering grounding

Checked **2026-10-11**; these are public reports, not access to private production implementations.

- [Anthropic, Scaling Managed Agents, Apr08 2026](https://www.anthropic.com/engineering/managed-agents): describes separate session, harness and sandbox interfaces, externally held credentials and recovery from an external event log. This supports retaining the current durable owner and composing an independently supervised runner. It does not imply replay is safe across this project's Unknown effects.
- [Anthropic, How we contain Claude, May25 2026](https://www.anthropic.com/engineering/how-we-contain-claude): separates model behavior from environment boundaries and describes failures in startup/config/proxy trust. Inference for this project: validate startup inputs and keep tokens outside candidate execution; a local config/listener must still enforce its boundary.
- [Anthropic, Infrastructure noise, Feb05 2026](https://www.anthropic.com/engineering/infrastructure-noise): reports that resource enforcement changes agentic benchmark outcomes and recommends documenting resource guarantees and kill ceilings. This motivates precise resource identity and separate load/quality evidence; its measured percentages are not this project's results.
- [Anthropic, Demystifying evals, Jan09 2026](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents): treats multi-turn execution, grading and recorded outcomes as distinct parts of the evaluation. Preserve the existing evaluator/denominators and attach serving faults to their real attempts instead of filtering them away.

**VI:** Nguồn2026 giúp chọn boundary và phép đo, không cho ta mượn reliability hay speedup của họ. Cùng nguyên tắc tách session/harness/sandbox vẫn phải chứng minh các crash window của implementation này bằng test riêng.

## Pre-change source identity and handoff

| File | SHA-256 |
|---|---|
| `service/api.py` | `5bc9b10e25287f068bfe924dbd38409505ba97dc7cb2a57ffc86161d01eb303c` |
| `service/storage.py` | `35f3eb2efc3a8dbda968321b60b6f6e3afd9f895d7151aa244c4a281f40a4990` |
| `service/workflows.py` | `2ffd9302bb5a0c865ddb8f39f2fe2d7b8580e85c600760c7e31fae09998f3919` |
| `service/engine.py` | `0df2d0e658f10efd5d5bcd7122d354443aaeb7c21d92d7f59aa53cb410c14e2c` |
| `service/execution.py` | `47ce32c3d9c1cb1e739c34adfac58b21b02a4b6bfcc1c0e8307f33d3929fb4b6` |
| `service/verification.py` | `a6076e4a8ba52aeabe519a7339ca2a7a8afce0eee76878fac46922fd473e6f8b` |

Changed artifacts: this audit and the serving specification only. No runtime/test source, store schema, historical evidence, provider setting, paid-execution policy or human mastery record changed by this lane. Next: integration owner reviews/freezes S-01–S-05, coordinates `storage.py` edits with skills recovery, implements the local service, then assigns independent adversarial tests/review. Full production readiness remains conditional on the explicit source and measured gates above.
