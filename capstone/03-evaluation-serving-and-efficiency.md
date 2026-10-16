# 03 — Evaluation, serving, and efficiency contract

**Status: proposed; 2026-10-08.** No production service has been deployed and no results below are achieved measurements. This contract extends H8, H10, H11, H13 and H15 in [the curriculum](../docs/02-mastery-learning-plan.md), using the Python/PostgreSQL/Temporal/object-store/Linux-isolation architecture in [the production design](../docs/03-production-architecture-and-stack.md). Inference initially uses a provider API. The current deterministic fixture lab establishes only the behaviors its tests exercise, not coding capability, OS containment, or production SLOs.

**VI:** Đây là hợp đồng về cách chứng minh hệ thống hoạt động. Những con số là mục tiêu đề xuất hoặc ví dụ tính toán; chỉ được chuyển thành kết quả khi có manifest, trace và phép chấm độc lập tương ứng.

## 1. Three questions; three separate scorecards

The [NV-S0 numerical reference](07-reference-implementation-spec.md#nv-s0-frozen-cpu-numerical-contract) adds local mathematical evidence only. Its public development cases do not join the 42-definition coding population, create held-out data, authenticate a candidate executable or count as accepted tasks. Later GPU metrics must preserve this contract's denominators/resource accounting and the [NV1 trusted measurement boundary](07-reference-implementation-spec.md#nv1-an-independently-measured-gpu-coding-workload).

| Scorecard | Question | Evidence |
|---|---|---|
| Capability | Can the system produce an acceptable change on unfamiliar repository tasks? | Pinned tasks, independently graded patches, acceptance criteria, paired trials |
| Durability | Does it preserve intent and report effects honestly through failures? | Crash-window matrix, duplicate delivery, recovery logs, unresolved-effect ledger |
| Serving | Can it sustain the declared workload within cost and latency limits? | Arrival replay, admission decisions, queue/timing traces, complete spending ledger |

Do not substitute one for another: durable execution can preserve a wrong solution; fast inference can accelerate a failed task. The public [Anthropic infrastructure experiment](https://www.anthropic.com/engineering/infrastructure-noise) found that resource configurations altered benchmark outcomes. Accordingly, environment resources are part of the task contract. The production-default topology has a planner, **at most two patch workers**, one integration owner, and an independent verifier; the gated research profile in §4 may select 1/2/4 patch workers. These are roles and authority boundaries; they need not be five simultaneous model processes. Deterministic verification need not call a model at all.

**VI:** Cần biết thất bại do không giải được bài, mất state, hay không đủ tài nguyên đúng lúc. Nếu trộn ba loại thành một điểm số, không thể chọn đúng hướng sửa.

## 2. A workload registry for difficult repository work

Create a versioned registry before comparing designs. Use fresh/private or permissioned repository tasks, plus public benchmarks as external calibration. Partition by repository family and time where feasible; prevent sibling fixes and near-duplicates crossing development and held-out splits. The benchmark author must not tune a hidden test after seeing which candidate it would favor. A task is difficult because it requires evidence, constraints and integration, not merely because its transcript is long.

| Tier | Required task structure | Proposed trial deadline |
|---|---|---:|
| T1: bounded repair | Real failing behavior, code navigation, a small patch and regression protection; meaningful negative cases | 15 minutes |
| T2: coordinated change | Several files/interfaces, compatibility constraints, integration tests, at least one plausible misleading hypothesis | 60 minutes |
| T3: long-horizon integration | Feature/migration or cross-component fault; multiple milestones, environment setup, design tradeoffs, complete end-to-end verification | 180 minutes |

Deadlines are initial engineering choices, not estimates of expert-human completion time. A T3 task should require at least three independently checkable acceptance criteria and preserve earlier behavior. Include changes such as migrating a service interface with rollback compatibility or fixing a concurrency bug across persistence and workers. Do not infer long-horizon competence from a collection of tiny independent edits.

**VI:** Task dài phải có các quyết định phụ thuộc lẫn nhau: sửa bước sau có thể làm hỏng bước trước. Đây mới là phép thử giữ invariant và tích hợp, không phải ép agent chạy lâu bằng nhiều bước vô ích.

Each manifest must pin task/spec revision, repository and base commit, allowed paths, dependency lock and image digest, architecture, CPU/RAM/disk/process quotas, network/credential policy, setup command, deadline, model/harness/schema revisions, budget ceilings, and grader artifact hashes. Record source provenance and known contamination concerns. Store developer-visible acceptance criteria separately from private grading assets. Verify that a trusted reference patch passes, a no-op fails where appropriate, and malformed/environment-breaking patches receive intelligible outcomes. Log manifest deviations; do not quietly repair the environment mid-comparison.

**VI:** Manifest biến “chạy cùng task” thành phát biểu kiểm chứng được. Khác image, internet, RAM hoặc base commit nghĩa là điều kiện thí nghiệm đã khác, dù tên issue giống nhau.

## 3. Independent acceptance, not self-reported completion

The candidate exports a patch against the pinned base and a manifest of intentional added files. A fresh verifier applies only allowed changes in its own Linux execution environment. Its protected tests, dependencies, success record and credentials are outside candidate write authority. Capture patch-application failures, test outcomes and resource usage. Grade behavior, compatibility and regressions; do not reward a particular implementation unless the spec requires it. For T3, use an acceptance rubric with explicit evidence for each criterion. Human review of maintainability/design can supplement tests; blind reviewers to experimental arm where practical.

A **verified patch** passes the preregistered automated contract. An **accepted task** additionally passes required review. Record both dates and decisions. A model reviewer is advisory unless separately validated; agreement between related models is not independent proof. Keep invalid-task findings in an exclusion ledger, adjudicate without viewing arm labels where possible, and rerun both arms if a correction changes the task.

The tier deadline is an **execution deadline**: a trusted passing receipt for the exact candidate must exist before the final fenced eligibility write samples the authoritative database clock and checks the cutoff under the task lock. Eligibility becomes durably confirmed after commit; this is not an exact commit-time deadline guarantee. Required human review has a separately preregistered deadline and effort rubric, identical across arms; it can occur later without extending execution. Report both time-to-verified-patch and review-inclusive acceptance time. Late review is a separate status transition over an already eligible immutable artifact, not permission for new model/tool work. Cancellation before eligibility prevents later eligibility; withdrawal afterward preserves historical evidence but revokes current eligibility. Audit review can still be recorded, but withdrawn results do not count as accepted releases. An expired or cancelled task cannot be restarted by a reviewer action.

**VI:** Test pass chưa chắc đáp ứng ý định người dùng; human review cũng không nên là cảm tính không có rubric. Tách verified và accepted để biết thời gian đang mất ở kiểm thử hay quyết định chấp nhận.

## 4. The baseline and bounded multi-agent experiment

The following single-agent/two-worker pilot remains the service baseline. The [target-role research contract](06-target-role-and-research-contract.md) adds a later 1/2/4-worker comparison and one allocation-policy intervention using the same runner and scoring rules. Freeze `profile_id`, validated `patch_slot_limit`, total resource limits and all role counts in each manifest. Research runs with four workers require the runtime's isolation/recovery/capacity gates; a large synthetic scheduler run alone does not establish coding capability. Research-development data and held-out confirmation data remain separate.

**VI:** Không thay pilot thành một cuộc thi thêm nhiều compute. Bản mở rộng dùng cùng cơ chế đo và invariant, nhưng profile được khai báo rõ để không nhầm kết quả research với SLO production.

Baseline A is one agent with the same pinned model identifier/version and generation settings, tools, retrieval, context policy and verifier. Candidate B uses planner → up to two workers → integrator → verifier. A role-specific model mixture is a separate treatment, not an isolated test of coordination. Give each worker an isolated workspace and a bounded deliverable; only the integrator publishes the candidate patch. Share one atomic budget ledger. Assign task/trial IDs before scheduling; interleave or randomize arm order within provider/model-version windows. Pin seeds where available without claiming provider inference becomes deterministic.

Run a **36-task diagnostic pilot**, 12 per tier, with three independent trial attempts per arm: 216 task attempts total. Begin with smaller smoke batches; this is a design, not authorization to purchase those runs. Freeze the pilot before using its outcome to choose a change, and reserve a later held-out confirmation set. Repeated attempts expose instability but do not create 108 independent tasks per arm.

**VI:** Pilot giúp tìm failure mode và ước lượng variance. Nếu dùng chính 36 task để thử mười thiết kế rồi chọn người thắng, cần tập xác nhận mới; không được gọi đó là bằng chứng tổng quát.

Use common **aggregate ceilings** for dollars, input/output tokens, elapsed task time, tool compute, and model concurrency. All planner/worker/integrator calls, retries, reviews and wasted branches count. Use identical inference concurrency limits across arms where feasible; internal parallel calls are a documented treatment difference. Exact realized tokens, dollars and time cannot generally all match because token prices, cache mix and early stopping differ. Therefore compare under the same resource envelope, report actual consumption, and add separate dollar-matched and deadline-matched sensitivity analyses. Never give B two full budgets because it has two workers. Do not force a solved baseline to waste its remaining budget.

**VI:** “Matched budget” là cùng cơ hội tài nguyên và cùng cách tính, không phải che phần planner hoặc failed branch khỏi hóa đơn. Nếu hai phương pháp không cùng dùng hết budget, phần tiết kiệm đó là kết quả cần giữ.

## 5. Metrics, clocks, and honest termination

Use monotonic elapsed clocks inside a run and correlated event IDs across services. Capture `submitted`, `admitted`, `worker_started`, `first_model_request`, `first_useful_token`, `tool_started/completed`, `patch_submitted`, `verification_completed`, `review_completed`, and terminal reason. Record provisional stream retries distinctly. Primary clocks start at submission so admission delay cannot disappear.

| Metric | Definition and reporting |
|---|---|
| Accepted-task rate | Accepted outcomes / all valid assigned task attempts under EV-04; include infrastructure failures and post-assignment cancellations; also report task-averaged rates |
| Time-to-verified-patch | Submission to first independently passing candidate; failed attempts have no event, not a zero latency |
| Acceptance completion curve | Fraction of all valid assigned attempts accepted by each elapsed time under EV-04; assigned rows never submitted remain non-events in the denominator |
| Cost per accepted task | Total experiment spend, including failures/retries, divided by accepted tasks; undefined if none accepted |
| Latency | p50/p95/p99 queue, model TTFT, tool, verification and end-to-end components, with sample counts |
| Coordination overhead | Planner/integration spend, merge conflicts, duplicate investigation, stale handoffs and discarded patch work |
| Reliability | Recovery time, duplicate effects, unknown effects, cancellation lag and leaked resources |

**VI:** Chỉ tính latency trên task thành công có thể làm hệ thống hay bỏ cuộc trông nhanh hơn. Luôn đặt cạnh completion curve và tỉ lệ fail; với ít mẫu, p99 gần như chỉ là một order statistic rất không ổn định.

Outcome categories include `accepted`, `verified_pending_review`, `review_rejected`, `review_deadline_exceeded`, `candidate_failed`, `budget_exhausted`, `deadline_exceeded`, `cancelled`, `infrastructure_failed`, `policy_blocked`, `invalid_task`, and `effect_unknown`. Pending review and unknown effects can later resolve through restricted reconciliation paths; they are not successful terminal results. Preserve underlying causes such as dependency failure, rate limiting or rejected stale edits. An execution deadline is a failure to meet that product contract, not a sample to delete. For time-to-event analysis it can be recorded as right-censored at the deadline, but censoring alone does not identify eventual success. Budget exhaustion and model-driven cancellation can be informative censoring/competing outcomes. Report them explicitly; do not assume censoring is independent. Operational interruptions of an experiment have a separate administrative-censoring flag. Publish raw counts and unconditional completion, plus conditional capability diagnostics with denominators and retry policy.

**VI:** `Unknown` sau một remote mutation cần reconciliation; không ép nó thành success hay model failure. Timeout là điều người dùng thực sự gặp, dù trong phân tích thống kê có thêm nhãn censored.

## 6. Statistical claims and release gates have different meanings

Report per-task paired differences, confidence intervals and outcome cross-tabs. Bootstrap the appropriate sampling unit: tasks, or repository clusters when tasks share material dependencies. With few repositories, cluster uncertainty is itself weakly estimated; show repository-level results. [Anthropic's statistical guidance](https://www.anthropic.com/research/statistical-approach-to-model-evals) motivates pairing and clustering. Estimate discordance and effect sizes in the pilot, then compute sample requirements for the prespecified practically meaningful gain. Neither “three trials” nor an overlapping pair of marginal confidence intervals establishes equivalence. Adjust for multiple comparisons or clearly label exploratory analyses.

**VI:** Một gate sản phẩm có thể nói “đủ tốt để thử nội bộ”, nhưng scientific claim cần nói rõ quần thể task, độ bất định và effect tối thiểu. Hai tiêu chuẩn không thay thế nhau.

Proposed gates below are **starting targets for a restricted internal canary**, subject to pilot calibration before freezing the release protocol:

| Area | Proposed gate | Limit of inference |
|---|---|---|
| Grader validity | Reference passes and negative controls fail on every included task; all manifest deviations explained | Does not prove grader completeness |
| Diagnostic quality | At least 70%/50%/30% accepted attempts for T1/T2/T3, reported separately | Feasibility thresholds, not frontier parity or population guarantees |
| Comparative quality | No unexplained tier regression above 5 percentage points; no superiority claim without a powered held-out paired study | Pilot may not exclude a harmful regression |
| Recovery | All enumerated crash windows covered; zero duplicate effects and zero falsely successful Unknown outcomes in 100 injected scenarios | Zero observed failures is not zero failure probability |
| Admission/load | p95 admission response <500 ms; p95 warm start delay <10 s at declared load; report rejects and cold starts | Conditional on measured load and resources |
| Cancellation/cleanup | p95 cancellation acknowledgement <2 s; confirmed local process cleanup <10 s; zero leaked test workspaces after TTL cleanup | Remote effects may remain Unknown |

Treat a boundary violation or dishonest success as a release blocker. A pilot with ambiguous quality results permits further experiments, not a claim that B is better. Under IID assumptions, zero failures in 100 observations still leaves an approximate 95% upper failure bound near 3%; correlated fault scenarios weaken even that interpretation. Canary scope, rollback thresholds and human review remain explicit.

**VI:** Các target thấp/cao bao nhiêu phải phù hợp nhiệm vụ thực tế; không lấy chúng làm thành tích trước khi chạy. Một lỗi tenant isolation quan trọng hơn vài điểm pass rate nên là hard gate riêng.

## 7. Serving contract: queues, context, and sandbox lifetime

The API service plane is FastAPI + PostgreSQL + Temporal + object storage + isolated Linux workers, calling provider inference. Submission checks authority, configured ceilings and tenant quotas, then reserves a bounded queue entry and returns a durable queued/accepted identity or structured rejection. Runtime admission separately reserves the applicable budget exposure and physical capacity before dispatch; an authorized spending ceiling is not itself an additional charge or dispatch reservation. Use separate limits for active model requests, runnable tools and retained sandboxes. Human waiting can release runnable/model capacity after checkpoint and confirmed quiescence. A retained or unconfirmed sandbox still occupies its physical patch slot; lease expiry alone cannot free it. Avoid starving small interactive tasks behind long autonomous tasks; evaluate per-class queues or weighted fairness, including aging and explicit priority policy.

For stable arrivals, `L=λW`. At **2 tasks/minute** and mean residence **6 minutes**, the system has **12 tasks in flight** on average. This is an illustrative calculation, not a measured capacity. If each task uses two minutes of active sandbox compute and there are six equivalent execution slots, `ρ≈λS/c=2×2/6=0.667`. Long tails, burst arrivals and shared dependencies can still create bad p95 latency. Measure arrival rate separately from completion throughput; closed-loop generators can hide overload by slowing submissions. Include a fixed-rate open-loop replay and track dropped/rejected work.

**VI:** 12 task đang tồn tại không có nghĩa cần 12 GPU decode cùng lúc. Phải phân biệt đang chờ model, chạy tool, giữ workspace hay chờ người. Queue metric cần mẫu số gồm cả việc bị từ chối.

Track sandbox states `provisioning`, `active`, `idle`, `checkpointing`, `suspended`, `destroying`. Record billed lifetime, CPU time, disk bytes, resume delay, and orphan cleanup. Test idle cutoffs rather than assuming one optimal TTL. Snapshotting should preserve workspace evidence and pending-effect metadata; it does not undo external actions. [Cursor's cloud-agent account](https://cursor.com/blog/cloud-agent-lessons) describes environment checkpointing and separating loop, machine and conversation state. In this capstone those mechanisms remain proposed until implemented and fault-tested.

**VI:** Giữ VM nóng đổi tiền lấy thời gian resume. Nếu tool đang có effect chưa rõ, tắt máy và restore snapshot không tự làm effect đó rõ hơn.

## 8. Cost and cache economics with an illustrative ledger

For disjoint provider-metered categories, use

`C = p_u U + p_w W + p_r R + p_o O + C_tools + C_sandbox + C_verifier + C_storage`.

U/W/R/O are uncached input/cache-write/cache-read/output tokens; prices are dollars/token. Some providers include cached tokens inside total input, so normalize without double counting. Hidden reasoning, failed billed calls and repeated branches count. For constant prefix P and per-turn growth Δ, uncached cumulative input is `NP + ΔN(N−1)/2`. Prefix caching reduces repeated prefill but not all attention work or total billed context. Record reused-token fraction, prefix-break locations, provider usage and wall-clock improvement separately. Compaction may reduce future cost while losing evidence or breaking cache; quality must be measured alongside savings.

Report settled charges, in-flight reservations and unresolved billing liabilities separately. Cost per accepted task remains provisional while potentially billed dispatches are unsettled; show a conservative exposure bound alongside observed spend instead of dropping unknown charges. Late receipts update settlement even after cancellation, without restoring execution authority. Hosted API timings expose client-observed TTFT, stream intervals and total response time; provider queueing, prefill and decode compute are not separately measured unless the provider supplies those timings. Do not relabel a client timing estimate as a GPU measurement.

**VI:** Cache hit là cơ chế, không phải mục tiêu cuối. Một prompt dài không cần thiết có thể hit rất cao mà vẫn tốn tiền, chậm và khó suy luận hơn prompt ngắn đúng thông tin.

**Synthetic example:** choose prices `$2/M uncached`, `$0.20/M read`, `$10/M output`, with no write-premium category. A hypothetical attempt uses U=20K, R=180K, O=10K: model cost is `$0.04+$0.036+$0.10=$0.176`. Six sandbox minutes at an assumed `$0.002/min` add `$0.012`; verification adds `$0.008`; total is **$0.196**, excluding storage for this example. Forty such attempts cost **$7.84**. If 24 are accepted, cost/accepted task is **$0.3267**, not $0.196. These are invented input assumptions, not vendor prices or achieved outcomes. Measure tier-specific distributions.

**VI:** Chi phí những lần thất bại phải được phân bổ vào kết quả được chấp nhận. Nếu fan-out tăng success nhưng tăng tổng chi phí nhanh hơn, cost/accepted vẫn xấu đi; cần nhìn cả quality, latency và cost cùng lúc.

Self-hosted GPU inference is a separate optional experiment. Freeze model, precision, topology and engine; compare against the same API-backed harness behavior before cost conclusions. Replay warm appends, cold starts, idle gaps, compaction and eviction. [PPD](https://arxiv.org/abs/2603.13358v2) reports why later-turn routing differs from first-prefill routing; [vLLM/Mooncake](https://vllm.ai/blog/2026-05-06-mooncake-store) supplies a concrete workload-specific cache-sharing study. These motivate hypotheses, not promised capstone speedups. Report GPU memory/transfer/queue limits and quality changes from quantization. No GPU is required for the initial service or durability contract.

**VI:** API service scaling và GPU inference scaling là hai lớp khác nhau. Không được dùng kết quả benchmark inference để tuyên bố task coding được giải tốt hơn.

## 9. Six prioritized ablations and the release packet

| Priority | One change and falsifiable hypothesis | Measurements and negative control |
|---|---|---|
| 1 | Independent clean verification rejects environment-tampering successes | Known wrong patches; false acceptance/rejection; trusted reference unchanged |
| 2 | Digest-bearing retrieval reduces stale edits under concurrent updates | Stale-edit rate and accepted tasks at equal context budget; unchanged files control |
| 3 | Bounded 1/2/4-worker scaling, then one allocation-policy change at fixed N | Paired quality, latency, all-role cost and overhead; T1 as low-parallelism control; profile admission gates and held-out confirmation |
| 4 | Evidence-preserving compaction lowers spend without losing constraints | Constraint probes and task quality; deliberately omitted-constraint control |
| 5 | Idle suspend/resume reduces sandbox spend within a resume-latency budget | Lifetime, resume p95, lost state, Unknown effects; always-warm baseline |
| 6 | Cache-aware admission/routing helps repeat turns without starving cold tasks | Completion latency by class, hit fraction, rejects and fairness; stale-residency control |

Run them in order: first establish trustworthy measurement, then capability/coordination, then efficiency. Freeze one main endpoint per experiment; publish failures and null results. The release packet contains registry/manifest hashes, raw paired outcomes, grader controls, cost ledger, latency/completion curves, crash matrix, workload generator configuration, supported scope, and rollback runbook. Every figure identifies whether it is simulated, measured locally, provider-reported, or projected. Promotion proceeds fixture → isolated single task → diagnostic batch → held-out validation → limited canary; no stage is claimed complete merely because its document exists.

**VI:** Kết quả âm có giá trị nếu chỉ rõ hypothesis nào bị bác bỏ và bottleneck ở đâu. Bài kiểm tra cuối: giải thích được tại sao thêm worker làm cache hit tăng nhưng time-to-verified-patch xấu đi, rồi thiết kế trace nhỏ nhất để kiểm chứng nguyên nhân.

## 10. Normative research requirements: EV-01–EV-08

“Must” below defines a proposed acceptance condition, not completed work. These requirements operationalize C4–C6 in the [role contract](06-target-role-and-research-contract.md); they do not describe Anthropic's private implementation. The irreversible research decision is revealing held-out outcomes: once used to choose a design, that set becomes development evidence. M0 establishes task validity; M6 freezes experiments and analysis; M7 establishes independent use.

**VI:** Một experiment có ba thứ phải khóa trước: can thiệp gì, giữ gì giống nhau, và kết quả nào có thể bác bỏ giả thuyết. Giữ lịch sử quyết định giúp người khác phát hiện việc đổi tiêu chí sau khi đã thấy điểm.

### EV-01 — Registry and grader validity

Every included task must have a stable ID, tier, repository family, provenance, immutable base, developer-visible requirements, protected grader digest and split assignment. Before results are observed, annotate branch dependencies and expected integration difficulty; these are task attributes, not labels inferred from which arm wins. Calibration tasks are separate from the 36-task diagnostic pilot. A trusted reference must pass; no-op and planted wrong-patch controls must fail the relevant requirements. Record flaky-test detection, retry rules and dependency provisioning failures. Invalidating a task requires a reason, adjudicator and affected run IDs; apply a corrected task/grader to complete comparison blocks, never only the losing arm.

**VI:** Grader là dụng cụ đo; trước khi đo agent phải biết dụng cụ có phân biệt lời giải đúng và sai đã biết hay không.

### EV-02 — Frozen manifest and output records

Freeze and hash one manifest before dispatch. References may point to immutable objects; secrets must be referenced by scoped identity rather than copied into it.

| Record | Mandatory fields and contract |
|---|---|
| Experiment | ID, hypothesis, primary contrast/endpoint, development or held-out split, registry digest, analysis revision, assignment seed, planned rows, stop rules, owner and freeze time |
| Task/trial | Task/base/grader IDs, trial ID, arm, submission identity, review rubric/cutoff, execution limit, allowed capabilities, inclusion decision |
| Treatment | Bare baseline or candidate topology; profile and N; all role counts; allocation/context/retrieval/tool policies; model identifier/settings; harness/schema revisions |
| Resource envelope | Aggregate USD and token limits, rate snapshot, call concurrency, CPU time/core quota, RAM/disk/process/network limits, per-environment minimums, deadline and cleanup reserve |
| Environment | Image/dependency digests, architecture, setup recipe, verification environment, allowed network, warm/cold policy and evidence of capacity |
| Attempt result | Outcome plus cause, timestamps, eligibility and review receipts, candidate/tree/grader digests, spend/reservations/unknowns, actual resources, deviations and trace references |
| Analysis artifact | Included/excluded row IDs, immutable raw-result digest, code/config revision, uncertainty method/seed, tables/figures, limitations and decision |

Reject incomplete manifests before costly dispatch. An unavailable pinned model version is a recorded deviation that blocks the affected comparison; silently resolving an alias to new weights is not reproducibility. Provider nondeterminism and unavailable internal revisions remain explicit limitations. Store later settlement/review facts as append-only corrections with an analysis cutoff, preserving prior reports.

**VI:** Manifest không chỉ ghi “model X, N=2”. Nó phải chứa đủ điều kiện để giải thích chênh lệch: thời gian chờ, máy, quyền tool, chi phí cả coordinator và luật review. Hash chứng minh byte không đổi; không chứng minh nội dung đúng.

### EV-03 — Assignment and execution order

The diagnostic design remains **36 tasks × 3 trials × 2 arms = 216 attempts**. Construct the full assignment table before scheduling. Within tier and provider-version/time blocks, randomize or balance arm order; retain the chosen schedule, seeds and deviations. Run comparison members near each other under matched declared load, avoiding unrecorded co-tenancy. Each trial starts from a fresh pinned environment and independent session; prevent cross-trial artifact leakage. A system retry stays inside its attempt's budget; rerunning a failed trial creates an additional labeled observation, not a replacement row. Provider seeds, where supported, do not make model outcomes deterministic or pair random streams perfectly.

**VI:** Cùng task là cặp so sánh hữu ích, nhưng chạy A buổi sáng và B lúc provider quá tải vẫn tạo confound; lịch chạy cũng thuộc experiment.

### EV-04 — Estimand, clocks and missing outcomes

Let `Q_tar=1` when task `t`, arm `a`, trial `r` has valid execution eligibility under the runtime deadline contract and required positive review by the fixed review cutoff, without a disqualifying withdrawal under the preregistered rule. Otherwise `Q_tar=0` at the analysis cutoff, with its reason retained. For `T` valid tasks and equal `R` planned trials, report `q_a=(1/T) Σ_t [(1/R) Σ_r Q_tar]`; the paired contrast is `Δ=(1/T) Σ_t [mean_r Q_tBr − mean_r Q_tAr]`. Units are proportions; multiply by 100 for percentage points. Weighting tiers/repositories differently requires declared weights before observing outcomes.

All assigned valid attempts remain in the primary denominator, including infrastructure failure, budget/deadline exhaustion, post-assignment cancellation, unresolved effects and missing review. An assigned row lost before submission is an infrastructure failure; it cannot disappear. Invalid-task adjudication may exclude complete task blocks with an exclusion ledger and sensitivity results. An administratively interrupted study must be marked incomplete: show assigned/started/completed counts, conservative not-yet-accepted rates and the interruption reason; do not present it as the planned completed study. Retain pending versus definitively failed labels even when both contribute zero accepted outcomes at cutoff.

Verification-event time and review-event time are different. Use unconditional cumulative fractions over the same assigned denominator; do not estimate success speed only among winners. Deadline censoring can support a separately justified time-to-event analysis, but no independent-censoring assumption is granted for model abandonment, budget exhaustion or infrastructure failure. The database eligibility decision timestamp, durable confirmation timestamp and client-observed acknowledgement are separate fields.

**VI:** Ví dụ hai arm cùng được giao 10 bài: A nhận 6 bài, B nhận 7 bài nhưng có 2 lần lỗi hạ tầng. Mẫu số B vẫn là 10, không phải 8. Nếu bỏ lỗi hệ thống, ta đang đo một sản phẩm tưởng tượng luôn có hạ tầng hoàn hảo.

### EV-05 — Resource control and complete accounting

Compare equal aggregate ceilings, not per-worker budgets. Include planner, integration, verification, retries, abandoned work and cleanup. Retain settled spend and conservative outstanding exposure separately; report model-review cost and human-review minutes, with an explicit human cost rule if monetized. Enforce token categories without double counting; provider usage is billing evidence, not a FLOP measurement. Record actual CPU-seconds, memory peaks, retained sandbox time and call concurrency as well as configured caps. If four workers need a larger physical envelope, publish that treatment difference and limit the causal claim accordingly. Neither equal dollars nor equal tokens alone establishes equal inference compute.

**VI:** Cùng trần tài nguyên cho phép đo hiệu quả sử dụng. Tài nguyên thực dùng là outcome phải báo cáo, không phải ép hai arm tiêu bằng nhau.

### EV-06 — Analysis, held-out confirmation and stopping

Freeze one primary contrast, a practically meaningful effect or non-inferiority margin, significance/interval convention, target population and task/repository sampling unit. Use pilot discordance/variance to justify the later held-out sample; do not invent a powered sample size before these inputs exist. Resample complete paired task blocks, or repository blocks when dependencies require it, preserving repeated trials. Report raw cross-tabs, per-tier/per-repository results, uncertainty and subgroup sample sizes. Secondary comparisons are multiplicity-adjusted or explicitly exploratory. A wide interval is inconclusive, not equivalence.

Choose N and the allocation rule on development data; freeze both before held-out confirmation. Access to held-out outcomes is logged and delayed until the planned batch or a preregistered safety stop. Stop for a boundary violation, budget exposure beyond the authorized envelope, corrupted grading, material model/environment drift, or the frozen attempt/spend/time cap. Pause affected work, retain all rows, document repair and specify whether a new experiment is required. Do not stop early for apparent success unless a valid sequential decision rule was frozen in advance. Costs and review outcomes may settle later; analysis versions expose changes.

**VI:** Hạ tầng lỗi có thể buộc dừng để sửa ngay; đó là safety stop, không phải cách chọn thời điểm điểm số đẹp nhất. Held-out chỉ còn giá trị xác nhận khi ta chưa dùng nó để chỉnh policy.

### EV-07 — Scaling first, allocation second

Keep three identities distinct: bare single-agent baseline A, candidate N=1 with coordination/integration overhead, and candidate N=2/4. The original pilot compares A against candidate N=2. The later scaling study adds N=1/4 only to the frozen research subset needed for that question; reuse N=2 observations only when registry, protocol, resources and time/version blocks are compatible, otherwise document why reruns are required. Do not automatically add another full factorial across every tier, model, context and policy.

At one selected, frozen N, compare static allocation against one progress-aware policy. Freeze observable inputs, decision boundaries and tie-breaking; log observation IDs, previous/new allowances and reason. Redistribution may reclaim only safely unused allowance; uncertain liabilities stay reserved. Both arms retain the same total ceilings and coordinator/verification reserves. Report starvation, conflicts, discarded work and critical-path stages beside quality/cost/time. Three tested N values support local comparisons, not extrapolation to hundreds of workers.

**VI:** N=1 có coordinator giúp đo riêng overhead của thiết kế; baseline một agent thuần giúp so sản phẩm. Hai câu hỏi cần giữ hai identity riêng.

### EV-08 — Inspectable evidence and independent reproduction

**Bounded source progress, 2026-10-10:** [the failure-to-regression adapter](../research/failure-regression-spec-2026-10-10.md) captures failed verification and Unknown dispatch, preserving exact identities, complete task costs and development lineage. [Verification](../research/failure-regression-verification-2026-10-10.json) covers these data controls. Fresh candidate repair, held-out confirmation and independently reproduced model-quality results remain the requirements below; the adapter does not output accepted trials or alter denominators.

Produce one compact evidence view from existing traces: requirement → DAG version → accepted owner/attempt → action/receipt → integrated tree → verifier → review. Link both successful and rejected branches, including stale epochs and unknown effects. Each causal explanation must name an observation and an intervention that could falsify it; correlated long model calls alone do not prove provider queueing or GPU saturation. Another person must reconstruct one table and rerun one declared experiment from the packet, recording environment differences and critique. Until that happens, independent reproduction remains pending. Huy's explanation and unseen-fault diagnosis are separate human evidence.

**VI:** Người review cần lần từ kết luận về raw event được, không chỉ xem ảnh dashboard. Nếu nói “integration là bottleneck”, phải chỉ ra nó nằm trên critical path và thử thay đổi có thể bác bỏ cách giải thích đó.

## 11. Normative operations requirements: OP-01–OP-08

These requirements define a restricted production operating envelope. A service is operable when it can admit bounded work, preserve acknowledged intent, expose honest progress and recover under known failures. The initial scope remains one team, allowlisted Python repositories and reviewed patch artifacts. Two synthetic tenants exercise access separation. Actual external service readiness is conditional on measured gates.

**VI:** Production bắt đầu từ lời hứa có giới hạn: nhận được bao nhiêu việc, lúc nào từ chối, khi chết máy còn giữ được gì. Thêm endpoint không tự tạo ra lời hứa đáng tin.

### OP-01 — Admission and idempotence

Authenticate tenant/repository authority before durable admission. The same tenant/idempotency key and canonical payload must return the same task identity; changed payload conflicts. Return a durable queued/accepted identity or a structured rejection reason; a timed-out acknowledgement is resolved by lookup/retry of that identity. Queued work consumes a bounded queue entry; runnable tools, physical sandboxes and model dispatches consume separate capacity only through their admission gates. Dispatch atomically checks current authority, deadline, tenant/service limits and per-dispatch liability. Distinguish authorized task ceilings from held dispatch reservations to avoid counting the same budget twice. A stale worker or repeated delivery cannot acquire another accepted effect by changing transport IDs.

**VI:** API timeout chỉ nói client chưa nhận được câu trả lời; lookup bằng cùng identity mới cho biết task đã được nhận hay chưa.

### OP-02 — Backpressure, fairness and lifetime

Freeze queue capacity, maximum wait, scheduling weights/aging, provider-call limits, runnable-tool limits and physical environment caps in the workload manifest. The proposed progression is one active task, then four active tasks with the default two-worker limit where physical capacity permits. Reject excess work before claiming durable acceptance; expiration of an already accepted queued task remains a visible deadline outcome. Apply bounded retry/backoff to retryable provider failures without exceeding deadlines/reservations. Never increase concurrency in response to rate limiting. A lost or retained sandbox counts until confirmed teardown/fencing under the runtime contract. Test fixed-rate bursts and sustained overload, and report queue/rejection/starvation by class and tenant.

**VI:** Queue vô hạn chỉ chuyển overload thành chờ rất lâu. Giới hạn phải có trước lúc nhận việc để deadline còn là lời hứa có nghĩa.

### OP-03 — Telemetry and clock contract

Every authoritative event must carry service incarnation and tenant/task/generation/node/attempt/action/dispatch IDs as applicable, event sequence, ownership epoch, configuration identity and artifact references. Persist authoritative receipts before relying on them; sampled tracing cannot be their only record. Record stage start/end, retries, tokens, charges, reservations, queue depth, physical slots and rejection reasons. Use monotonic clocks for local duration, trusted server/database time for deadline decisions, and wall-time correlation with synchronization/skew checks across processes. Mark uncertain intervals rather than inventing exact ordering. Keep prompts, credentials and private code out of unrestricted telemetry; use access-controlled artifact references and explicit retention.

**VI:** Trace để debug có thể bị mất vài span; ledger quyết định authority và tiền thì không được phụ thuộc sampling. Hai lớp dữ liệu phục vụ hai lời hứa khác nhau dù cùng dùng task ID.

### OP-04 — SLI denominators and release windows

Freeze workload, sample minimums, measurement window and target before the release batch. The targets in §6 are proposed calibration inputs; changing one requires a new version and explanation. Record failures beside latency percentiles.

| Indicator | Population and failure treatment |
|---|---|
| Admission response | All valid authenticated submission attempts at the declared arrival rate; include rejects in latency, report accept/reject separately; transport timeout is a failure, not a dropped sample |
| Warm start | All admitted attempts labeled warm before dispatch; measure submission → first runnable worker; no-starts/deadline failures reported alongside p95; cold attempts remain separately visible |
| Cancellation | All valid cancellation requests; acknowledgement and confirmed local teardown are distinct; unresolved remote effects retain Unknown |
| Acknowledged intent durability | Every acknowledged task identity must remain reconstructible in tested fault windows; missing task or accepted artifact reference blocks release |
| Task completion | All assigned/submitted valid attempts under the declared contract; tier quality and completion curves remain separate from API availability |
| Resource accounting | All created sandboxes and billable dispatches, including failed/rejected/stale work; unknown liabilities and unconfirmed cleanup remain in totals |

No measured samples means “unmeasured,” never 100% reliability. Small sample counts cannot support a stable p99 or rare-failure claim. For a restricted canary, minimum duration/counts and error-budget thresholds remain design choices to freeze before exposure, not numbers inferred after a favorable run.

**VI:** Một request được từ chối nhanh có thể làm latency đẹp nhưng không phục vụ được người dùng; phải nhìn cả mẫu số, reject rate và completion.

### OP-05 — Staged release and canary

Promote fixture → isolated task → diagnostic batch → frozen held-out validation → restricted canary only with the corresponding evidence. Before canary, require grader controls, isolation/fencing/budget/restore tests, a pinned release manifest, complete runbooks and an identified operator. Start allowlisted internal tasks with review required; record release version per task. Any tenant escape, stale authoritative acceptance, fabricated pass, lost acknowledged intent or budget-bound violation stops new admission and quarantines affected publication immediately. Breached frozen latency/quality/queue thresholds trigger the declared drain/rollback decision. Collect enough declared traffic to assess the window; a quiet canary is not success evidence.

**VI:** Canary giảm phạm vi tác động để kiểm chứng vận hành. Nó không thay thế bài fault injection và cũng không tự tạo bằng chứng nếu không có workload.

### OP-06 — Rollback and active-run compatibility

Test old/new workflow, schema, tool and artifact compatibility before promotion. Pin active runs to compatible behavior or use an explicit tested migration; a code rollback cannot erase durable history or remote effects. Exercise stop-admission, drain, cancel and publication-revoke independently. Preserve reconciliation/settlement access while execution is revoked. Use a release rollback that restores a known compatible version and verifies in-flight tasks, references and budgets; do not roll back database state by deleting inconvenient events. Record the trigger, operator, affected task set and outcome.

**VI:** Rollback phần mềm chỉ đổi code chạy tiếp. Một request đã tính tiền, một patch đã công bố hay một record đã commit vẫn có lịch sử riêng; runbook phải xử lý chúng thay vì giả định thời gian quay ngược.

### OP-07 — Incident response and restore

Cover provider outage, stuck task, uncertain effect, worker loss, grader outage, queue overload and storage recovery. Each runbook names detection evidence, authority to act, immediate containment, reconciliation steps, verification of recovery and review artifacts. A combined database/workflow/artifact restore must begin in an isolated, no-admission mode. Restored epoch values describe historical claims; they cannot revive authority or prove that pre-restore workers are dead. Before connecting restored state to execution, fence the entire pre-restore service incarnation: old schedulers, workflow/outbox workers, gateways, effect/billing reconcilers and sandbox supervisors. Confirm termination or an enforced execution boundary for old environments; unconfirmed physical environments retain their capacity allocation.

Activate a fresh, non-reused service-incarnation identity accepted by every trusted admission/acceptance gateway, as required by RT-09. Incrementing the maximum epoch found in a stale backup is insufficient. Do not reuse old leases or let an old callback acquire current authority. The restore drill must inject delayed pre-restore commands/results after activation and show that they cannot advance authoritative state. If the deployment cannot fence an old control-plane writer or execution environment, remain stopped until that boundary is established.

A current-incarnation recovery operator/reconciler then reconstructs effects and charges after the backup frontier from retained dispatch records, provider receipts and infrastructure evidence. Credential/token revocation cannot undo or prove termination of an external request already accepted by a provider. Preserve uncertain effects, conservative liabilities and affected scope limits; do not resume a task/account whose missing history prevents bounding exposure or avoiding duplicate effects. Verify accepted references against exact object bytes, rebuild workflow/database relationships, reacquire fresh ownership and prove that replay cannot create an unsafe repeated effect before lifting admission. Raw evidence from old actors may support reconciliation through the new trusted authority; it grants those actors no write access.

Freeze the failure model, backup cadence, retention, recovery-point objective (maximum tolerated lost state) and recovery-time objective before operational use; measure achieved values. Within the declared durability failure model, acknowledged authoritative intent/receipts require no unrecoverable loss; a positive-RPO disaster scenario must be disclosed separately and cannot satisfy that guarantee. A backup file without a successful restore does not pass. Record incident timelines and repair actions without rewriting prior failures.

**VI:** Backup cũ có thể chứa epoch nhỏ hơn một worker vẫn còn sống. Nếu chỉ restore rồi tăng epoch cũ, hai thế giới có thể cùng tự nhận là owner. Cần cắt quyền thế giới cũ, cấp incarnation mới và đối soát effect sau thời điểm backup; thu hồi token không làm một request đã được provider nhận biến mất.

### OP-08 — Conditional scale expansion

N=4 remains a gated research configuration after M2/M3 and physical-capacity proof; production default remains two. Raising task concurrency or worker count requires a new operating envelope, open-loop load/fault tests, fairness/cleanup evidence, settled cost and a bounded rollback. Large-scale readiness requires measured control-plane throughput, storage/queue behavior, provider quotas, isolation and failure-domain recovery at the proposed scale. Deterministic scheduler fixtures may identify limits; they cannot establish coding quality. Expand only when the measured bottleneck and research question justify it, retaining the same C1–C6 evidence chain.

**VI:** Scale lớn là một giả thuyết cần kiểm tra lại. Nếu bốn worker chưa thắng vì dependency và integration, mua thêm máy không giải được câu hỏi khoa học đang mở.

## 12. Decisions required before implementation or live runs

| Freeze point | Unresolved choice | Required output |
|---|---|---|
| M0 | Target repository/base, calibration/development/held-out tasks, grader/rubric | Validated registry and controls; no invented fixture commit |
| Before relevant build slice | Queue/retention limits, physical quotas, rate/price bounds, authority and failure policy | Reviewed versioned engineering contract with invariants, failure cases and a distinguishing experiment; human learning evidence assessed separately |
| Before any live batch | Provider/model/settings, allowed spend, full resource envelope, review cutoff and effort | Complete EV-02 manifest; unresolved spend is a run blocker |
| Before held-out confirmation | Primary contrast, meaningful margin, sample justification, stopping/analysis policy | Frozen EV-06 plan derived from development evidence |
| Before canary | Workload/traffic, SLI windows/sample minimums, rollback triggers, backup/RPO/RTO, operator | OP-04–OP-07 protocol and demonstrated prerequisite gates |

These are decisions to make at the corresponding milestone, not authorization to launch runs now. No production trace by Huy has been recorded yet. This specification preserves the target learning and build requirements. Their initial proposed status is historical; [current coverage](08-implementation-coverage.md) distinguishes delivered bounded mechanisms from unmeasured broader requirements.

**VI:** Thiết kế chi tiết không có nghĩa phải đoán số budget hay chọn model ngay hôm nay. Ta chốt contract, invariant và thí nghiệm phân biệt trước khi AI build phần đã được cho phép. Việc em tự học, dự đoán và transfer được đánh giá riêng; quyền tiêu tài nguyên vẫn cần đúng authorization.

**Context mechanism evidence, 2026-10-10:** [the offloading verification](../research/context-offloading-verification-2026-10-10.json) checks an old-tool-only sentinel absent from the dispatched projected payload, preserved in raw history and recovered by a subsequent authorized byte read. This is a retrieval-assisted scripted mechanism control, not model recall quality or a measured cost improvement. Canonical JSON request identity differs from raw HTTP serialization identity; both are retained. The all-assigned population, denominators, fixed budgets and semantic post-activation evaluation requirements remain unchanged.


## Current bounded readiness delivery — 2026-10-11

The [current dependency/evidence plan](../research/system-readiness-plan-2026-10-11.md) adds typed skills post-turn recovery (M5/RT-09), persisted atomic pending-task caps and configured loopback fixture serving (M7/SYS-08/OP admission), durable per-instance local-Docker cleanup (M3/RT physical-slot ownership), and trusted RMSNorm qualification preparation (H12/NV-S1 partial). The [coverage register](08-implementation-coverage.md) owns implementation status and open gates; these additions do not replace the broader requirements above.

A restored checkpoint supplies data, a fresh claim supplies authority, a terminal container observation permits physical-slot release, and a verification receipt permits candidate evaluation. None substitutes for the others. The service currently runs fixed authored fixtures; a real live repair service still needs the separately frozen workload/provider/operation envelope. GPU preparation runs no generated code and defaults to no execution. Paid execution and human mastery remain unchanged.

**VI:** Ta hoàn thành các boundary nhỏ có thể kiểm chứng và giữ nguyên production contract. Đừng suy “cleanup xong” thành “task được retry”, hoặc “HTTP trả200” thành “service đạt SLO”.
