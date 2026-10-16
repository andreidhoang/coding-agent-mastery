# Target role and research capability contract

**Decision date: 8 October 2026. Target: Anthropic, Staff Research Engineer, Multi-Agent Scaling.** The [official posting](https://job-boards.greenhouse.io/anthropic/jobs/5442680008) lists an annual salary of **$500,000–$850,000 USD**. It is tied at the top of our checked shortlist and most directly aligned with the existing capstone. This is a project-fit decision, not a global compensation ranking or a guaranteed offer.

**NVIDIA target added 10 October 2026:** [Senior Research Engineer — AI Coding Tools, JR2017020](https://jobs.nvidia.com/careers?query=JR2017020&pid=893394980530), advertised Level 6, shares the same core project. Its US annual base range is **$272,000–$431,250** at L6, with equity/benefits additional. The current portal lists the role; the application redirect was not functioning in our check. Section 9 and the [dated audit](../research/nvidia-role-alignment-2026-10-10.md) define the bounded specialization and remaining gaps. This adds a company-specific evidence path without replacing the original research question or claiming equivalent seniority from title/pay.

The posting emphasizes agent-team experiments, reliable platforms, long-horizon evaluations, resource allocation and clear findings. It explicitly does not require formal credentials, publications or prior multiagent/RL work, while seeking significant software engineering, ML or research-engineering experience and substantial end-to-end ownership. Logistics permit a bachelor's or equivalent education/training/experience; locations are San Francisco/New York/Seattle, normally at least 25% office attendance, with conditional visa sponsorship. Our route builds capability evidence; it does not erase Staff-level expectations. Recheck at application time.

**VI:** Ta chọn role vì công việc thực tế khớp project và mức lương nằm trong nhóm cao đã kiểm tra. Không cần tạo mục tiêu PhD phụ; cần biến quá trình học và vận hành thành evidence về engineering, research judgment và ownership thật. Không thể bảo đảm kết quả tuyển dụng 100%.

## 1. Keep one project and one learning sequence

Keep H0–H15, M0–M7 and the chosen service stack. The product remains a durable coding service with a two-worker production default. The role-focused result adds a research question: **under a fixed aggregate resource envelope, when does a team solve a hard coding task better or faster, and what causes returns to diminish?** No new framework, model training stack or GPU engine is required to answer that initial question.

The first-principles cycle is observe → hypothesize → predict → intervene → measure → explain → reproduce. Under [D012](../context/decision-log.md) AI builds the reference; under [D046](../context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates) Huy learns it through production traces that start from real runs. Huy's own work stays separately attributed, and the research gates below are not earned by AI delivery.

**VI:** Một project đủ sâu có thể nối được nhiều skill mà không tạo nhiều project rời rạc. Câu hỏi scaling buộc ta dùng lại state, context, scheduler, budget và verifier đã học; đó là lý do hợp lý để mở rộng.

## 2. Six capabilities that matter most

| Capability | First-principles constraint | Existing learning and build | Evidence and discriminating gate |
|---|---|---|---|
| C1 Correct, bounded execution | Text is a proposal; effects require valid inputs, authority and observable outcomes | H1–H3, H7; M1–M2 | Trace a typed action to bytes/processes; reject partial calls and unauthorized effects; explain a planted tool/process defect |
| C2 Durable ownership | Crash and message delay separate actual effects from recorded knowledge | H4, H11; M3 | Recover through intent/effect/receipt windows; reject old epochs; account for unknown effects, retained sandboxes and unsettled charges |
| C3 Long-horizon information and decomposition | Observations become stale, memory is finite, and dependencies constrain parallel work | H5–H6, H10; M4–M5 | Restore on a fresh environment, retain constraints and provenance, detect a semantic merge conflict, explain a changed dependency |
| C4 Trustworthy empirical research | Gains may come from extra resources, a weak grader, contamination, task selection or chance | H8, H15; M0/M6 | Preregister one hypothesis, use negative controls and held-out tasks, pair outcomes, retain failures and report uncertainty |
| C5 Scaling and resource allocation | Parallel speed is limited by serial work, communication, contention and integration | H10, H13; M4/M6 | Explain a 1/2/4-worker curve; compare one allocation policy under fixed total limits; locate the measured bottleneck |
| C6 An independently usable research platform | A result must be reconstructible, diagnosable and useful to another person | H11, H15; M6/M7 | Reproduce from a manifest; produce a compact evidence-linked trace; diagnose an unseen fault and defend a decision in writing |

These clusters cover the selected role's central work. Fluent Python/async programming, Git, Linux processes, transactions, graph algorithms, probability, statistics and quantitative writing are prerequisites embedded in the relevant modules. Remediate a gap when observed; do not create a separate survey curriculum. H9 interfaces support integration. H12 model/cache fundamentals explain serving behavior. Actual H14 training, accelerator kernels and large GPU fleets remain optional specialization.

**VI:** C4 và C5 là chỗ phân biệt “xây được agent” với research engineering. Em phải biết một con số có đáng tin không, rồi giải thích nguyên nhân và quyết định phân bổ tài nguyên dựa trên nó. C1–C3 làm nền để phép đo đó có ý nghĩa.

## 3. Derive the optimization objective

Let `N` be the maximum concurrent patch workers, `B` the total task spending ceiling in USD, `D` the execution deadline in seconds, and `Q_i` the binary accepted-task outcome under the fixed review rule. All coordinator, worker, integration, retry and grading costs count. For the declared task population, choose a policy `a` to maximize `Pr(Q=1 and execution eligible by D)` subject to `spent + reserved ≤ B` and physical resource limits. Keep completion time and cost as separate outcomes rather than hiding them in an arbitrary weighted score. Human review follows its separate fixed deadline.

For `m` valid assigned attempts, report `q_hat = sum(Q_i)/m`, retaining infrastructure failures and missing outcomes under the evaluation contract's fixed cutoff. Also report the task-averaged estimand and handle task/repository clustering as specified there. Compare acceptance completion curves, total settled spend and liabilities, and cost per accepted task. Hosted API dollars/tokens are resource proxies, not measured GPU FLOPs; provider-internal compute remains unavailable unless exposed. A fixed dollar ceiling and a fixed token ceiling need not be equally binding.

Execution eligibility uses the final fenced database decision-time rule in [the runtime contract](02-runtime-contracts-and-recovery.md), with a trusted passing receipt already present. Record the decision timestamp and durable commit observation separately; a worker-supplied completion time cannot backdate eligibility. The [evaluation protocol](03-evaluation-serving-and-efficiency.md) fixes the denominator, review cutoff and handling of unresolved results before execution.

**VI:** Tăng N không được tăng B cùng lúc rồi gọi chênh lệch là teamwork. Cũng không được chỉ so những run đã thành công. Policy tốt cần tạo thêm giá trị trong cùng điều kiện, hoặc tiết kiệm tài nguyên mà vẫn giữ mức chất lượng đã định nghĩa.

For fixed divisible work, a useful baseline model is `T_N = T_serial + T_parallel/N + I_N`, where every term has units of time and `I_N` is additional coordination/integration time. This assumes balanced branches, unchanged work, no queue contention and no quality change; it is a planning model, not a law of probabilistic coding agents.

**Synthetic example:** `T_serial=4 min`, `T_parallel=12 min`, and additional `I_N` of 0/3/5 minutes for N=1/2/4 gives total times 16/13/12 minutes. Four workers yield only a one-minute improvement over two in this example. Real traces must establish whether extra investigation, conflict, queueing or verifier work changes the terms.

**VI:** Nếu bước tích hợp hoặc test không chia được, thêm worker không làm phần đó nhanh hơn. Nhưng agent còn có thể thay đổi cả lượng công việc và xác suất tìm được giải pháp; vì vậy phải đo quality cùng với timing, không áp dụng Amdahl như một lời tiên tri.

## 4. Three additions for the scaling research target

### A1 Controlled scaling experiment, inside M4 and M6

Keep the original single-agent reference, and extend the candidate topology to N=1/2/4 on a frozen research-development set, followed by separate held-out confirmation. Candidate N=1 still has coordinator/integration overhead; it is not the original bare single-agent baseline. Reuse compatible frozen N=2 runs where task/protocol identities match, or explain why new observations are needed; do not duplicate a whole pilot by default. N counts patch workers, excluding coordinator/integrator/verifier roles, whose costs still count.

Fixed model/settings, tools, grader and task bases reduce confounds. Apply the [evaluation contract's complete shared resource envelope](03-evaluation-serving-and-efficiency.md): dollars/tokens, deadlines, aggregate tool compute/CPU/RAM capacity and model concurrency where feasible. Pin per-environment minimums. If N=4 needs more aggregate capacity to be viable, record that treatment difference and avoid attributing its gain solely to coordination. Stratify task structure/horizon before observing outcomes. The initial study establishes behavior only at tested scales.

Use `production` profile with `patch_slot_limit=2`. A separately selected `research` manifest may set 1, 2 or 4 after M2 isolation and M3 recovery gates, physical capacity and resource ceilings are demonstrated. Reject unsupported values before dispatch. Changing a running profile requires a new run/generation; a model cannot raise the ceiling. Retained or unconfirmed obsolete sandboxes still occupy physical slots. Provider-call limits and total infrastructure admission remain separate.

Start with deterministic DAG/fault/load fixtures to establish mechanics. Live coding evaluations follow their engineering gates and a declared spend envelope. Simulated scheduling throughput is not coding capability. Do not fit a broad scaling law from three N values. If confidence intervals are wide, report uncertainty and collect evidence rather than declaring a winner. Larger teams are a later measured capacity expansion, not an initial deliverable.

**VI:** N=4 là experiment được khai báo, không phải tự nâng production capacity. Các invariant vẫn giống N=2: owner, sandbox, budget và verifier đều phải giữ đúng. Curve ba điểm giúp chẩn đoán phạm vi nhỏ; chưa chứng minh hệ thống cho hàng nghìn agent.

### A2 One fixed-budget allocation intervention, inside M6

Compare a static allocation policy with one progress-aware policy. Static policy partitions worker allowances in advance and retains explicit coordinator/integration/verification/cleanup reserves. The candidate can redistribute only unused, safely releasable allowance at recorded decision boundaries, using observations available at that time: unmet dependencies, verified progress, failures and estimated remaining work. It cannot reclaim uncertain billed liabilities or invent hindsight signals.

Study allocation at a fixed N first. Choose the policy on research-development data and evaluate it once under the frozen held-out protocol; do not jointly tune N, model, context and allocation then attribute all gains to scheduling. Report time-to-verified-patch, accepted-task rate, spend/exposure, discarded work, conflicts and starvation. A useful null result may show that investigation or grader latency dominates the supposed benefit.

**VI:** “Dynamic” không tự tốt hơn. Nếu policy lấy lại tiền của một request timeout nhưng vẫn có thể bị tính phí, nó đang phá budget invariant chứ không tối ưu. Quyết định phải dùng bằng chứng thực sự có tại lúc đó.

### A3 Researcher-readable evidence and independent use, inside M7

Generate a compact report from existing traces: requirement/DAG versions, actor/attempt ownership, critical-path stages, candidate/verification digests, failed branches, unsettled effects/costs, and links to the original events. Use the existing reporting tools; a new dashboard is unnecessary. A reader should be able to reconstruct why an outcome was accepted and where time/resources went without reading every model message.

Invite an independent collaborator/reviewer to rerun one experiment from the frozen manifest, critique the conclusion and verify that it follows from the raw outcomes. Prepare a 20-minute system/research review and an unseen-fault/requirement transfer exercise. Huy must explain a design, diagnose the fault and defend or revise the conclusion. Assistance remains allowed and attributed. If no independent reviewer is available, mark this gate pending rather than manufacturing peer evidence.

**VI:** Ownership được xây bằng hành động có hậu quả và feedback thật: viết contract, vận hành, sửa lỗi, bảo vệ một kết luận trước người khác. Project ở scale nhỏ là evidence có giá trị nhưng không được gọi thành kinh nghiệm vận hành fleet frontier.

## 5. Evidence packet and readiness

Use one versioned evidence packet in the existing project: repository/config identities, architecture/contracts, task and grader manifests, raw outcomes, scaling/allocation analysis, fault/restore evidence, compact trace report, decision memo and independent reproduction feedback. Every claimed improvement links to a run; every personal capability links to Huy's session evidence. AI-written code and explanations remain attributed.

| Gate | Required demonstration | Current status |
|---|---|---|
| Learning | Huy's production traces touching C1–C6, in the [trace log](../docs/05-mastery-tracker.md) | None recorded yet |
| Platform | Actual isolated/durable runs and defined operating envelope | Bounded source and local integration evidence delivered; broader source gaps and operated envelope pending in [coverage](08-implementation-coverage.md) |
| Research | Held-out scaling/allocation result with controls and uncertainty | Not measured |
| Independent use | Another person reruns and reviews evidence | Pending |
| Staff-level readiness assessment | Substantial ownership, judgment and communication judged against the current role | Not established |

Readiness is a reasoned assessment, not a hiring probability or an automatic badge. Employer level calibration, competing candidates, opening availability and eligibility remain outside the curriculum's control. No PhD detour is added; additional scale evidence is pursued when the small-scale experiment and operating record justify it.

**VI:** Mục tiêu controllable là evidence đầy đủ và trung thực cho các capability. Không đánh dấu “job-ready” từ code AI đã giao, và không biến “100% phủ skill map” thành “100% được tuyển”. Nếu gate thiếu, nó chỉ ra experiment hoặc bài transfer cần làm tiếp.

## 6. Effort and next action

**Historical estimate:** these ranges predate the current reference delivery and do not prescribe daily time or remaining effort. Re-estimate only the selected unmet gate; use the [current readiness plan](../research/system-readiness-plan-2026-10-11.md) and actual human evidence.

The three additions reserve **24–40 additional engineering hours** beyond the previous capstone: M4 +6–10 h, M6 +12–20 h, M7 +6–10 h. The updated milestone table includes this increment: capstone integration/research/hardening totals **104–180 h**, alongside the existing **104–156 h** learning route, giving **208–336 h** overall. These are estimates, not deadlines or mastery guarantees; failed gates and meaningful scale expansion can require more. No new H-module or technology stack is introduced.

The next learning action is the first production trace, from the G1 live call. Authorized engineering follows the specification/coverage gaps independently of Huy's traces. The role targets change why later experiments matter. The original effort range above excludes the later NVIDIA specialization, which requires a scoped estimate after workload/toolchain discovery.

**VI:** Ta cập nhật đích và evidence cần tạo, nhưng không nhảy qua H0 để chạy swarm. Kỹ năng đi tới role này được tích lũy qua mỗi bài dự đoán, debug và kết luận dựa trên dữ liệu.

## 7. Role requirements to engineering and research evidence

The [official role](https://job-boards.greenhouse.io/anthropic/jobs/5442680008), rechecked on **8 October 2026**, supplies the work categories below. The requirement IDs, technologies, exercises and pass conditions are our design decisions. This is a traceability map to public responsibilities, not Anthropic's internal interview rubric or architecture.

| Public role responsibility, paraphrased | First-principles skill | Capstone contract and learning | Evidence a reviewer can inspect |
|---|---|---|---|
| Design and interpret team experiments | Turn a vague claim into an estimand, controlled treatment, falsifier and uncertainty statement | C4; H8/H15; M0/M6; SYS-10; EV contract | Preregistered protocol, all outcomes, paired analysis, null result retained, conclusion scoped to observed population |
| Explain scaling across team size, resources and horizon | Model dependency limits, contention, duplicated work and changing solution probability | C3/C5; H6/H10/H13; M4–M6; SYS-05/06/08 | 1/2/4 curves, dependency/horizon strata, critical-path trace and fixed-N allocation comparison |
| Build reliable large-team infrastructure | Preserve ownership and resource invariants under delay, duplication, loss and saturation | C1/C2; H1–H4/H7/H11; M1–M7; SYS-02/03/04/08/11; RT/OP contracts | Fault matrix, controlled load sweep, stale-owner rejection, retained-liability accounting, operating limit and restore record |
| Make long-horizon evaluation trustworthy | Distinguish real progress, stale evidence, weak graders and task/environment failure | C3/C4; H5/H6/H8; M0/M5/M6; SYS-05/07/10 | Protected grader controls, versioned milestones, fresh-environment recovery and invalid-task adjudication ledger |
| Make team behavior understandable | Preserve causal identities and compress evidence without losing provenance | C6; H4/H11/H15; M3/M6/M7; SYS-09/12 | Compact report reconstructing one accepted result and one surprising failure from original events |
| Enable other researchers and communicate decisions | Provide stable interfaces, reproducible conditions and a defensible interpretation | C6; H9/H15; M7; SYS-01/12 | Independent rerun, documented feedback, 20-minute architecture/research review and decision revised when warranted |

**VI:** Cùng một component tạo nhiều loại evidence: budget ledger vừa chống overspend vừa làm phép so sánh fixed-budget đáng tin. Vì vậy ta thêm chiều sâu ở component chung, không thêm một framework riêng cho mỗi dòng job description.

The role also asks for substantial ownership, quantitative judgment, clear communication and attention to impact. Carry one issue from ambiguous requirement through design alternatives, implementation, measured failure, revision and operated outcome. Preserve Huy's actual reasoning and AI assistance separately. Include task permissions, data provenance, misuse-relevant capability boundaries and failure impact in the design review. A portfolio reader should be able to distinguish a chosen tradeoff from a copied default and a measured finding from a plausible story.

**VI:** Ownership không được chứng minh bằng số lượng file hoặc việc AI viết được code. Evidence nằm ở quyết định em hiểu, lỗi em chẩn đoán, feedback em xử lý và hậu quả vận hành em theo dõi. Việc nhờ AI hỗ trợ vẫn hợp lệ khi vai trò và hiểu biết của em được trình bày trung thực.

## 8. From bounded capstone to larger-scale evidence

The initial capstone demonstrates mechanisms at a small, declared scale. The posting includes very large teams; a four-worker study cannot establish that requirement by itself. Treat the remaining gap as a measured expansion decision after the initial service and research gates, not as an assumed outcome of the curriculum.

| Stage | Question answered | Evidence required before expansion |
|---|---|---|
| Deterministic mechanics | Do identities, limits, retries and recovery obey their contracts? | Fault and load fixtures with known outcomes; explicitly no coding-capability claim |
| Restricted coding study | Does bounded teamwork help on the declared task population and resource envelope? | Strong bare baseline, candidate 1/2/4 study, fixed-N allocation, held-out results and all costs |
| Operated canary | Can an actual user rely on the service within a documented workload? | Real authorized use, incident/rollback/restore evidence, measured SLOs and independent reproduction |
| Conditional scale expansion | Which control-plane or execution bottleneck appears as agents and horizon increase together? | Capacity plan, reproducible failure, root cause, mitigation and rerun; separate synthetic load from live coding capability |

For the expansion review, parameterize logical teams `N`, concurrent tasks `K`, task horizon `H`, model-call concurrency `C_m` and physical execution capacity `C_s`. Sweep one variable while holding the others and per-run envelope fixed, then test one justified interaction such as `N × H`. Declare workload semantics and physical resources. Measure database contention, outbox age, scheduler delay, workflow history growth, artifact traffic, sandbox occupancy and provider limits. Increase the tested bound only after resolving the observed limit and preserving the same correctness gates. Thousands of cheap simulated workers may find scheduler bugs; they do not establish the performance of thousands of coding agents.

The decision memo must answer: what failed first; why the evidence supports that cause; which alternative explanation was ruled out; what changed; what quality/cost/latency tradeoff followed; and where the result should stop being generalized. Choose the next scale from this evidence and an authorized resource budget. Actual expansion effort is outside the preliminary 208–336-hour estimate and must be estimated when its scope is known.

**VI:** Ta không che gap giữa project nhỏ và Staff role. Cách thu hẹp hợp lý là vận hành thật, tìm điểm gãy có bằng chứng, sửa rồi đo lại. Không tự đặt mục tiêu hàng nghìn agent trước khi biết bottleneck hoặc chi phí; cũng không gọi synthetic load là năng lực giải code.

## 9. NVIDIA coding tools evidence within the same project

Implementation was authorized on October 10, beginning with [NV-S0's frozen numerical reference](07-reference-implementation-spec.md#nv-s0-frozen-cpu-numerical-contract). That CPU foundation is now delivered with [source-bound verification](../research/nvidia-s0-verification-2026-10-10.json); GPU and subsequent stages remain pending. The five dependency slices are the engineering order; [coverage](08-implementation-coverage.md) records implementation. Logical traceability to the selected role is the objective, not a claim of 100% capability or hiring readiness.

Select **Senior Research Engineer — AI Coding Tools, JR2017020, advertised Level 6** as the NVIDIA target. The [audit](../research/nvidia-role-alignment-2026-10-10.md) compares current senior/principal postings, first principles and source evidence. A Lead Principal enterprise-platform role reaches the same checked base-pay ceiling but requires broader enterprise/Kubernetes architecture; do not add that scope to chase a title. The selected role's 12+ years, shipping record and in-person collaboration remain real requirements, not things a study plan can waive. Degree-equivalent routes do not imply experience-free hiring.

| Existing capability | NVIDIA-specific evidence | Owner and bounded change |
|---|---|---|
| C1/C2 Correct execution and ownership | Exact generated CUDA source → binary → independently verified hardware result under resource/cleanup controls | NV1; H3/H7/H12/H13; M2/M6; extend one build/verifier recipe |
| C3 Context and current knowledge | Versioned toolkit facts and a reproducible skill/tool activation reaching the actual request | NV2; H5/H6/H9; M5; reuse course contracts |
| C4 Trustworthy research | Numerical controls, matched hardware timings, one knowledge or profiler intervention, honest failures | NV1/NV2; H8/H13/H15; M0/M6; existing evaluator |
| C5 Resource efficiency | Kernel versus component versus task benefit; all-attempt search cost; unchanged shared envelopes | H12/H13; M6; extend metrics, not scheduling topology |
| C6 Reproducible research and use | Reviewed development-data lineage, independent reproduction and actual user feedback | NV3; H14/H15; M6/M7; existing evidence packet |

The [NV1–NV3 specification](07-reference-implementation-spec.md#nvidia-coding-tools-specialization) is the implementation authority. One CUDA workload, one knowledge/profiler profile and one reviewed data-promotion path are the complete initial addition. Actual GPU measurement is required for this specialization's performance evidence. API-backed inference still suffices; generic self-hosting, another agent framework, full compiler work and distributed training are not initial requirements. Code-model specialization is an actual duty of the role: until a justified fine-tuning study runs, report that gap explicitly instead of claiming data preparation or RAG covers it.

**VI:** Ta giữ sáu capability cũ và thêm evidence cụ thể cho NVIDIA. Existing attention/KV/trajectory code không bị viết lại. Điểm mới là agent dùng tool/knowledge để tạo CUDA change có oracle và measurement, rồi biến development evidence thành data có provenance. Không có phép tính “100% aligned” che phần kinh nghiệm và vận hành chưa có.

**Shared evidence foundation delivered, 2026-10-10:** [the bounded failure-to-regression adapter](../research/failure-regression-spec-2026-10-10.md) supports C4 evaluation and causal diagnosis and inspectable engineering evidence through two local runtime cases. [Review](../research/failure-regression-independent-review-2026-10-10.md) and [verification](../research/failure-regression-verification-2026-10-10.json) establish its bounded controls. GPU execution/performance, broader NV-S4 data use, model specialization, production operation and human mastery retain their existing gates; no role-readiness percentage follows from this addition.

**Bounded C2/C3 source progress, 2026-10-10:** [context offloading](../research/context-offloading-spec-2026-10-10.md) connects information selection to durable dispatch ownership and recovery. [Independent review](../research/context-offloading-independent-review-2026-10-10.md) checks exact request identity, current-projection retrieval and checkpoint lineage. This supports long-horizon information engineering and durable ownership within the existing project. Live semantic retention, runtime developer-knowledge/skill use, GPU optimization, operated service behavior and human transfer evidence remain separate requirements.

**Bounded C3 skills foundation, 2026-10-11:** capture, receipt-derived broker loading and accepted request disclosure now have distinct evidence. Use [frozen step-4 specification](../research/skills-disclosure-spec-2026-10-11.md), [independent review](../research/skills-disclosure-independent-review-2026-10-11.md), [verification](../research/skills-disclosure-verification-2026-10-11.json) and [exact request trace](../docs/06-reference-code-reading-guide.md#accepted-skills-catalog-request-and-resource-authority). Step4 adds exact catalog/tool/prompt/state/request identity, complete historical provenance, native mock HTTP and resource authorization from the emitting request's accepted loaded state. This strengthens shared C3/NV2 reliability evidence without adding a second runtime or permission system. It does not complete NV2 profiler/MCP work or prove performance benefit. Step5 typed recovery now has [separate evidence](../research/skills-recovery-independent-review-2026-10-11.md); no GPU result, live-model capability, human mastery or hiring readiness follows.

## Current evidence mapping — 2026-10-11

[Readiness delivery](../research/system-readiness-plan-2026-10-11.md) strengthens the same six capabilities: protocol/skills recovery and physical ownership support durable execution; atomic admission and actual child lifecycle support serving mechanics; independent faults, installed origins and retained failures support reproducible engineering; the trusted RMSNorm probe prepares numerical/measurement work. It supplies no live GPU/model result, operated fleet experience, completed role equivalence or hiring guarantee. Broader gaps remain in [coverage](08-implementation-coverage.md), without extra curriculum modules.
