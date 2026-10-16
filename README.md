# Coding-agent systems: build, trace, understand

**Current delivery, 2026-10-11:** [offline provider qualification](ops/runbooks/provider-qualification.md) now binds two native mock requests and receipt-derived evidence to an exact prepared repair, with immutable advisory handoff. [Verification](research/provider-qualification-verification-2026-10-11.json) records43 qualification tests,381 related regressions, six independent review controls and full installed rc4 acceptance. Paid/live gates remain pending.

**Earlier readiness implementation, 2026-10-11:** the [dependency and evidence plan](research/system-readiness-plan-2026-10-11.md) builds on the existing runtime with typed skills recovery, an authenticated loopback fixture service with atomic pending-task limits, explicit journaled Docker cleanup, and a trusted RMSNorm GPU qualification probe that defaults to no execution. Independent audits, frozen contracts, adversarial tests and installed-package acceptance have distinct evidence. [Coverage](capstone/08-implementation-coverage.md) separates source delivered from broader missing code and external qualification.

Live Nebius execution is authorized only for Huy's scoped hackathon path under [D042](context/decision-log.md#d042-live-execution-enabled-for-the-hackathon-path), after the required account/model/rates, frozen budget and task inputs are supplied. GPU rental and public hosted deployment remain disabled. This machine has no CUDA. The [release index](releases/README.md) preserves each candidate's exact identity; new source does not rewrite prior artifacts or inherit old test results. The reference uses authored fixtures and mocked model responses; it does not establish real coding quality or operated production. Repository access alone grants no credential, spending or deployment authority.

**VI:** Ba thứ phải tách rõ: code đã xây, môi trường đã kiểm thử, năng lực thật chưa đo. Recovery đúng là giữ evidence và chặn effect không đủ quyền; không phải cứ restart là gọi model/tool lại.

This workspace now contains an AI-written **reference codebase** for a bounded durable coding-agent service, plus evaluation, serving simulation and tensor-learning tools. AI built the reference under Huy's 8 October 2026 instruction. Since **16 October 2026** ([D046](context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates)), learning starts from production traces: a real run or a production codebase, traced down to first principles, with no mastery gates. Huy's own learning is recorded separately in the [trace log](docs/05-mastery-tracker.md).

**VI:** Bây giờ đã có code để lần theo từ nguyên lý xuống implementation. “Có reference chạy được” không có nghĩa em đã master, model giải được task lạ, hay service sẵn sàng production. Mỗi loại bằng chứng có cột riêng.

Start with [START-HERE](START-HERE.md), the [code-reading guide](docs/06-reference-code-reading-guide.md), and [current state](context/current-state.md). The original H0–H15 concept sequence remains canonical in [the learning plan](docs/02-mastery-learning-plan.md).

## Collaborate from GitHub

This private repository includes the current source, tests, core docs and agent context. Start with [CONTRIBUTING](CONTRIBUTING.md) for a minimal offline setup and agent read order. [Snapshot scope](docs/github-snapshot.md) explains omitted historical artifacts and pinned upstream links. Access is limited to invited collaborators.

## Run the reference

The NVIDIA AI Coding Tools specialization follows [NV-S0–NV-S4](capstone/07-reference-implementation-spec.md#ordered-implementation-slices). **NV-S0 is delivered:** a CPU RMSNorm numerical reference, independent oracle and negative controls, with [a visual/code trace](compute/README.md#nv-s0-rmsnorm-numerical-foundation), [review](research/nvidia-s0-review-2026-10-10.md) and [verification](research/nvidia-s0-verification-2026-10-10.json). Run `.venv/bin/python -m compute.rmsnorm` to inspect it. This workbench slice preserves the hackathon service and the original production contracts; trusted GPU preparation is now implemented under [its runbook](ops/runbooks/trusted-gpu-probe.md), while generated-kernel isolation, hardware measurements and later agent stages remain pending in [coverage](capstone/08-implementation-coverage.md).

```sh
uv sync --locked --extra dev
.venv/bin/python -m service doctor
.venv/bin/python -m service demo --output runs/my-first-reference
.venv/bin/python -m pytest -q tests/test_engine.py tests/test_provider_qualification.py
```

For the full suite, use the SDK and packaging-tool prerequisites in [CONTRIBUTING](CONTRIBUTING.md#validate-locally); the minimal install above supports the selected mock checks.

The demo uses an explicitly scripted model to repair a frozen synthetic issue tracker. It records requests/actions, changes separate worker workspaces, integrates exact trees, verifies known authored controls, and stops at **review eligible / review pending**. Its trace is generated from committed events. Default tests skip unavailable or unrequested external backends; those skips are not passes. The [implementation coverage](capstone/08-implementation-coverage.md) and [operations guide](ops/README.md) explain the real PostgreSQL/Linux/Temporal checks.

**VI:** Demo dùng đáp án script cố định để kiểm tra cơ khí của runtime. Nó giúp thấy data đi qua những boundary nào; không dùng pass của demo làm điểm capability của LLM. Muốn đánh giá model phải khóa model, giá, task population và phép đo riêng.

## What is implemented

| Layer | Code and purpose |
|---|---|
| Durable authority | `service/storage.py`: SQLite/PostgreSQL transactions, owner/controller fencing, shared allowances, effect/billing reconciliation, physical slots, DAG, events, outbox and review |
| Model feedback loop | `service/harness.py`, `protocol.py`, `providers.py`, `billing.py`: complete envelopes, exact provider artifacts, scoped tools, scripted, Anthropic and native Nebius transport |
| Offline qualification | `qualification.py`, `qualification_cli.py`: frozen manifest, native mock continuation, conservative billing, evidence-derived report and exact prepared-task advisory handoff; no live enablement |
| Supported repair | `repositories.py`, `repair_provider.py`, `repair.py`, `repair_verification.py`, `repair_reporting.py`: frozen inputs, approved provider, one worker, protected per-case Docker checks, clean checkpoint resume and exact diff/report |
| Execution and verification | `execution.py`, `integration.py`, `verification.py`: guarded edits, bounded Linux containers, exact source trees, an external behavior grader and protected receipt authority |
| API and workflow | `api.py`, `offline_server.py`, `serving_config.py`, `admission.py`, `workflows.py`: configured authentication, repository grants, resumable events, cancellation, Temporal activities and idempotent notification delivery |
| Context and retrieval | `context.py`, `context_retrieval.py`: deterministic offloading, explicit provider capability and digest allowlist; Harness/RuntimeStore bind the accepted projection to its exact canonical request |
| Recovery and inspection | `recovery.py`, `skill_recovery.py`, `environment_recovery.py`, `reporting.py`: typed checkpoint reconstruction, explicit per-instance Docker reconciliation, unresolved liabilities and a browsable trace |
| Workloads | [workloads](workloads/README.md): six calibration and 36 diagnostic definitions across 13 synthetic templates, known correct/incorrect controls |
| Research | [evals](evals/README.md): frozen assignments, complete denominators, paired uncertainty, allocation, synthetic scheduling/arrival experiments and bounded runtime-failure-to-regression evidence |
| Tensors and GPU preparation | [compute](compute/README.md): scalar/eager/SDPA attention, CPU RMSNorm oracle/eager/byte identities, KV/prefix mechanics, offline objectives, exact tensor ledgers and a disabled-by-default trusted CUDA qualification probe |

Dependencies are frozen in [uv.lock](uv.lock). The selected versions are reproducibility inputs, not a claim that every newest package is the best engineering choice. Architecture and review used Astra; bounded code and audit work used 6.1 Sol with coordinator integration. Sources, decisions and independently found defects are retained in [the architecture audit](research/implementation-architecture-audit-2026-10-08.md) and [code review](research/implementation-code-review-2026-10-08.md).

**VI:** Điểm đáng học nằm ở tradeoff: authority lock thô làm reasoning và concurrency test rõ hơn ở scale nhỏ, nhưng không được suy thành throughput tốt cho hàng nghìn agent. Chỉ thay lock hoặc tách service khi workload và profiler cho biết bottleneck thật.

The 2026-10-09 audit repairs separate raw provider receipt preservation from message acceptance and billing, preserve immutable result evidence on retries/settlement, await the actual Temporal memo API and retain stop signals across activity/history boundaries. Verification snapshots candidate inputs and latches transport failures outside expected candidate exceptions; container cleanup binds an instance nonce and immutable ID. New authority stores use schema 2's unambiguous identity keys. Existing schema 1 databases require an [explicit offline migration](service/migrations/002_identity-and-writer-protocol.md); constructor startup never silently upgrades them. The October9 checks passed **273 tests plus 15 subtests**, Ruff, and rebuilt wheel/image smoke validation with real local PostgreSQL/Docker/Temporal. Research repairs also protect cumulative cost and cache/tensor measurement semantics. The October9 verification record supplies the source identities for those outcomes; later delivery records cover later changes. The previous 154-test record remains dated historical evidence.

**VI:** Bản audit mới sửa những chỗ một kết quả có thể bị hiểu sai: HTTP body nhận đủ chưa đồng nghĩa tool được chạy, settlement tiền không được xóa result, và tên container không đủ chứng minh instance nào thuộc quyền cleanup. Migration đổi representation của ID, không khôi phục effect đã mất hoặc cấp quyền rolling upgrade.

## Boundaries still open

The reference is **not the complete production release** described by the original SYS/RT/EV/OP contracts. Graph replacement/replanning, automatic recovery of every active attempt, semantic/native context rollover, production retention/GC, fair admission queues, a generalized repository/live-model task runner, and operated SLO/backup/restore evidence remain incomplete or deferred. A configurable live harness exists and passes mock-transport tests; no paid inference or live capability study ran. CUDA performance, training improvement, hostile-tenant containment, independent human/fresh-machine reproduction and human mastery remain unestablished. See the [coverage register](capstone/08-implementation-coverage.md) for the precise distinctions.

**VI:** Những gap này là phần source còn thiếu hoặc bằng chứng chưa có; không gom tất cả thành “chỉ cần deploy”. Bước học có thể bắt đầu ngay trên reference hiện tại, còn engineering tiếp theo phải chọn đúng gap và test phân biệt nó.

## Preserved evidence and plans

- [Original first-principles map](docs/01-first-principles-and-system-map.md) and [production architecture](docs/03-production-architecture-and-stack.md).
- [Capstone contracts](capstone/README.md), [reference implementation spec](capstone/07-reference-implementation-spec.md), and [target-role contract](capstone/06-target-role-and-research-contract.md).
- [Original trusted lab](lab/README.md), pinned upstream provenance in [references](references/README.md), and [omitted local archive inputs](docs/github-snapshot.md#omitted-local-evidence).
- [Production trace log](docs/05-mastery-tracker.md): Huy's traces; no understanding is inferred from this implementation.
- [Learning/research audit](research/implementation-learning-research-audit-2026-10-08.md) and [workload evidence](research/workload-implementation-notes-2026-10-08.md).

The shared career direction includes Anthropic Multi-Agent Scaling and NVIDIA AI Coding Tools through [one role contract](capstone/06-target-role-and-research-contract.md). This project supplies inspectable engineering and study material; it is not an employment or seniority-readiness guarantee.

Run the new local evidence demonstration with `.venv/bin/python scripts/failure_regression_demo.py --output runs/my-failure-regression-demo` using a fresh directory. Inspect [the saved two-case packet — local-only](docs/github-snapshot.md#omitted-local-evidence): failed-verification causal generation remains 1 after the task advances to 2; Unknown exposure12 becomes spent9 while the effect remains Unknown. The fixed predicates test attribution/accounting, and the example declared AI reviews stay separate from the independent code review.

**VI:** Đây là vòng biến failure thành counterexample có identity và cost đúng. Nó chưa chạy patch mới để chứng minh sửa bug, chưa tạo held-out data và không mở paid execution.
