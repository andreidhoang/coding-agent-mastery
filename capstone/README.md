# Durable multiagent coding service capstone

The [NVIDIA Nebius hackathon profile](../hackathon/README.md), prepared October10, selects one supported live repair path and a submission deadline. It reuses this capstone; broader production requirements and the two-worker default remain intact. Its protocol implementation and evidence are tracked separately from the dated reference delivery.

The capstone's product target is a service that accepts a scoped software task on a pinned repository, coordinates bounded coding workers, survives defined failures, and returns a patch with independent verification evidence. An AI-authored reference now exists under `service/`, `workloads/`, `evals/` and `compute/`, with local integration evidence and explicit source gaps. The primary outcome remains **a correct, reviewable change within a declared time and resource budget**; reference delivery does not establish the complete production contract.

**VI:** Capstone nối toàn bộ curriculum vào một sản phẩm có hợp đồng rõ: nhận yêu cầu, thực hiện, chịu lỗi, kiểm chứng rồi bàn giao. “Long horizon” nghĩa là tiến độ và bằng chứng còn đúng qua nhiều lần dừng, đổi context hoặc đổi máy; không phải bắt model nói liên tục thật lâu.

AI builds the reference under [D012](../context/decision-log.md); since [D046](../context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates), Huy learns it through **production traces** that start from real runs, with no mastery gates. The [reference specification](07-reference-implementation-spec.md) and [implementation coverage register](08-implementation-coverage.md) describe the source, measured checks, partial behavior and pending operations. The next trace starts from the G1 live call; [the H0 runtime packet](../study/packets/H0-reference-runtime.md) and [the code-reading guide](../docs/06-reference-code-reading-guide.md) are reference material for it. H0–H15 is the concept reference; AI delivery is never recorded as Huy's understanding. [Starting guide](../START-HERE.md).

The [single target-role contract](06-target-role-and-research-contract.md) selects Multi-Agent Scaling research and defines six capabilities plus three focused additions. Keep the two-worker production default; a separately validated research profile studies 1/2/4 workers. GPU serving and model training remain optional. No new project or module sequence is added.

The same contract now includes the [NVIDIA AI Coding Tools target](06-target-role-and-research-contract.md#9-nvidia-coding-tools-evidence-within-the-same-project). Its bounded specialization connects agent-generated CUDA code to independent correctness, measured profiling, versioned developer knowledge and reviewed data lineage. [Research and role comparison](../research/nvidia-role-alignment-2026-10-10.md), [engineering contracts](07-reference-implementation-spec.md#nvidia-coding-tools-specialization). This specialization needs real GPU evidence for performance claims; it does not require self-hosting the coding model or expand the hackathon deliverable.

**VI:** Code reference đã có để làm đối tượng học: đi từ boundary nhỏ đến dòng code, state và bằng chứng thật. Thứ tự build-first do Huy chọn không tự hoàn thành mastery hoặc cho phép gọi local demo là production.

The specification retains an explicit traceability chain: **public role responsibility → capability C1–C6 → learning module → design review → SYS/RT/EV/OP requirement → implementation evidence → operated/research result**. Start a design review from [the role crosswalk](06-target-role-and-research-contract.md#7-role-requirements-to-engineering-and-research-evidence), then read the owning contract. `SYS` covers product/interfaces/trust; `RT` runtime correctness; `EV` experiments; `OP` serving/operations. The [milestone/design gates](04-build-sequence-and-mastery-gates.md) separate engineering readiness from human mastery under D012. Implementation status is assessed per component in the coverage register. Human mastery, operated production and held-out research gates remain pending.

The [2026-10-10 course audit](../research/course-audit-2026-10-10.md) adds bounded contracts for compaction, skills, LSP and failure-driven regressions inside [the existing specification](07-reference-implementation-spec.md#course-derived-extension-contracts--proposed-2026-10-10). Use its pinned source through the H5/H6/H8/H9 reading map; no second runtime, curriculum, vendor stack or benchmark population is introduced. These extensions do not automatically enter the deadline-bound [hackathon profile](../hackathon/README.md); that profile's required delivery work keeps its own priority.

**VI:** Mapping này cho biết “học điều gì để quyết định và chứng minh điều gì”. Spec chi tiết không bắt em đọc hết trước H0; mỗi lesson chỉ mở phần contract mà cơ chế đang học sẽ phục vụ.

## One project and six engineering priorities

| Priority | Component | The question you must answer | Suggested share of core engineering effort |
|---|---|---|---:|
| 1 | Durable state and recovery | After any crash, what happened, who owns the next step, and what may be repeated? | 25% |
| 2 | Independent verification | Which exact candidate passed which immutable checks under which environment? | 20% |
| 3 | Isolation and effect control | What can generated code read, change, call, or exhaust? | 15% |
| 4 | Context and evidence | What must the next model invocation know, and how is freshness established? | 15% |
| 5 | Bounded multiagent coordination | Which work is independent, who resolves conflicts, and when should fan-out stop? | 15% |
| 6 | Serving and efficiency | What limits verified task throughput and cost under load? | 10% |

These percentages are planning allocations, not measured component value. Evaluation accompanies every component. Start with one coordinator, at most two concurrent patch workers, one serialized integration owner, and a verifier with separate authority. Roles need not correspond to permanent model processes. Compare this configuration against a strong single-agent baseline before increasing concurrency.

**VI:** Phân vai giúp làm rõ trách nhiệm. Tăng số model không tự tạo thêm thông tin hữu ích; đôi khi chỉ nhân chi phí đọc cùng một repo. Verifier độc lập về quyền và môi trường mới là boundary quan trọng, không phải việc gọi thêm một LLM để nói “looks good”.

## Read in this order

For NVIDIA implementation, read [the ordered slices](07-reference-implementation-spec.md#ordered-implementation-slices) and [coverage](08-implementation-coverage.md) after this overview. Begin with NV-S0's CPU numerical contract, not a GPU deployment. The hackathon remains a separate delivery profile of the same production contracts.

1. [System specification and component map](01-system-specification.md): scope, architecture, interfaces, technology choices and one concrete hard task.
2. [Runtime contracts and recovery](02-runtime-contracts-and-recovery.md): identities, ownership, checkpoints, effects, budgets and crash windows.
3. [Evaluation, serving and efficiency](03-evaluation-serving-and-efficiency.md): task tiers, resource-matched comparisons, metrics, load tests and research ablations.
4. [Build sequence and curriculum integration](04-build-sequence-and-mastery-gates.md): eight milestones, implementation backlog, mastery exercises and release packet.
5. [Frontier evidence and design decisions](05-frontier-evidence-and-decisions.md): public evidence checked on 8 October 2026 and its limits.
6. [Target role and research contract](06-target-role-and-research-contract.md): first-principles skills, bounded additions, effort and evidence assessment.
7. [Reference implementation specification](07-reference-implementation-spec.md): implementation-first authority, component contracts and local/deployment evidence boundaries.
8. [Implementation coverage register](08-implementation-coverage.md): current implemented, partial and pending source/validation requirements.

This is the authoritative **capstone implementation plan**. The [H0–H15 plan](../docs/02-mastery-learning-plan.md) remains the concept reference; Huy's learning is recorded in the [trace log](../docs/05-mastery-tracker.md). The [general architecture chapter](../docs/03-production-architecture-and-stack.md) explains deployment stages; this folder chooses one path through them. `research/` contains supporting analyses, `references/` contains inspected source snapshots, and `archive/` preserves historical inputs. Do not create another competing curriculum when an experiment changes a design decision; update the relevant contract and its evidence.

**VI:** Một nguồn quyết định cho mỗi loại thông tin giúp tránh ba tài liệu đều tự nhận là plan chính. Concept học ở H-module; việc cần build nằm ở milestone; số đo phải trỏ tới run thật. Khi chúng mâu thuẫn, sửa mapping và decision record thay vì thêm một summary nữa.

## What counts as completion

The final demonstration submits a difficult multi-file change, loses a worker after a possible effect, resumes from durable evidence, rejects a stale worker result, integrates independent candidates, and grades the resulting tree in a clean environment. It also demonstrates cancellation, exhausted shared budget, a wrong patch rejected, and overload handled without losing accepted work. Deliver the resulting artifact and an honest quality/cost/latency comparison against the single-agent baseline.

| Current artifact | Current status |
|---|---|
| Role-aligned system specification, runtime/research/serving contracts and design gates | Written; proposed; open decisions close at their milestone |
| Existing [offline teaching lab](../lab/README.md) | Implemented; previous verification records 15 passing tests |
| Bounded service/reference grader and deployment adapters | Source delivered with local integration evidence; source gaps and operational limits remain in the coverage register |
| Live-model benchmark and sustained-load result | To measure |
| GPU serving or training experiment | Optional later research extension |
| Human learning | Recorded as production traces in the [trace log](../docs/05-mastery-tracker.md); not inferred from delivery |

The reference includes an inspectable harness core, SQLite/PostgreSQL state, Temporal workflow adapters, immutable artifact interfaces and bounded Linux execution. Dependency versions are pinned in `uv.lock`. API-backed inference remains the proposed first production path; live model/settings, prices, allowed spend, target repository and deployment configuration still require an explicit frozen run contract. Introduce a self-hosted model only for a measured workload or research question that warrants it.

**VI:** Hiện tại có thiết kế, lab lịch sử và code reference mới cùng các phép thử local. Ta học bằng trace production, bắt đầu từ call live G1, và tra H0–H15 khi cần khái niệm. Những gap về replacement/reconciliation tự động, graph revision, context rollover, queue fairness và vận hành vẫn được ghi rõ; phần em hiểu được ghi bằng trace thật của em, không suy ra từ code AI viết.

**Current bounded extensions:** the [failure-evidence adapter](../research/failure-regression-spec-2026-10-10.md) and [deterministic context offloading](../research/context-offloading-spec-2026-10-10.md) now have separate source-bound verification and review. Context acceptance is per dispatch in schema 2; it is not a mandatory task-wide mode or completed semantic compaction. Follow [coverage](08-implementation-coverage.md) for current evidence.

The [October10 offline candidate](../releases/README.md) retains its dated bounded M7 installed reproduction evidence. Later capture(step2), broker(step3) and accepted disclosure(step4) are checkout additions under [frozen step-4 specification](../research/skills-disclosure-spec-2026-10-11.md), [independent review](../research/skills-disclosure-independent-review-2026-10-11.md), [verification](../research/skills-disclosure-verification-2026-10-11.json) and [exact request trace](../docs/06-reference-code-reading-guide.md#accepted-skills-catalog-request-and-resource-authority). Step4 binds catalog/state/tools/prompt/history/request in context-v2 acceptance, validates complete durable source history and uses exact scripted/native mock requests. Same-response resources deny; later accepted loaded state permits frozen-capability resource reads. Broker-v1 cannot be promoted. Next is step5 typed checkpoint/fresh-owner recovery; the current opt-in returns an explicit unsupported-checkpoint result and refuses restore/pause. No new candidate, operated production, human mastery or paid execution follows; hackathon essential gates retain priority.

## Current bounded readiness delivery — 2026-10-11

The [current dependency/evidence plan](../research/system-readiness-plan-2026-10-11.md) adds typed skills post-turn recovery (M5/RT-09), persisted atomic pending-task caps and configured loopback fixture serving (M7/SYS-08/OP admission), durable per-instance local-Docker cleanup (M3/RT physical-slot ownership), and trusted RMSNorm qualification preparation (H12/NV-S1 partial). The [coverage register](08-implementation-coverage.md) owns implementation status and open gates; these additions do not replace the broader requirements above.

A restored checkpoint supplies data, a fresh claim supplies authority, a terminal container observation permits physical-slot release, and a verification receipt permits candidate evaluation. None substitutes for the others. The service currently runs fixed authored fixtures; a real live repair service still needs the separately frozen workload/provider/operation envelope. GPU preparation runs no generated code and defaults to no execution. Paid execution and human mastery remain unchanged.

**VI:** Ta hoàn thành các boundary nhỏ có thể kiểm chứng và giữ nguyên production contract. Đừng suy “cleanup xong” thành “task được retry”, hoặc “HTTP trả200” thành “service đạt SLO”.
