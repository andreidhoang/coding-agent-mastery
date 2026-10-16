# Build sequence and mastery gates

Design and later build one system through eight milestones. Every milestone has a design review before implementation and an executable evidence gate afterward. This document specifies proposed work; no milestone or human mastery is established by writing it. The [H0–H15 curriculum](../docs/02-mastery-learning-plan.md) supplies concepts; this sequence turns those concepts into a production candidate. AI may write initial implementations. Since [D046](../context/decision-log.md#d046-production-backward-learning-replaces-mastery-gates), each milestone's **Mastery:** line is an optional trace starter, not a gate; design reviews and exit artifacts remain the engineering gates.

Huy's current preference, [D012](../context/decision-log.md), is to audit/specify and build the reference first, then master its mechanisms. Use the [starting guide](../START-HERE.md), [current state](../context/current-state.md) and [coverage register](08-implementation-coverage.md). The milestone table preserves target acceptance contracts; delivered components are inspected and extended rather than rebuilt. Human learning evidence remains separate from authorized implementation.

**VI:** Milestone là contract cần chứng minh, không phải danh sách tất cả code còn thiếu. AI có thể build reference sau audit/design; mastery chỉ ghi khi Huy thực sự dự đoán, giải thích và chuyển điều kiện.

The role-focused capstone reserves **104–180 additional engineering hours beyond the curriculum's 52 study sessions**, including **24–40 hours** for the [three focused research additions](06-target-role-and-research-contract.md). These hours cover integration, experiments and hardening beyond module prototypes. Combined with **104–156 study hours**, the planning range is **208–336 hours**, roughly **18–28 weeks at 12 hours/week**. Reuse outputs and count existing pilot work once. Cloud waiting time, substantial scale expansion and deep GPU/training specialization are outside this estimate. The design reviews below refine the same scope; they are not extra projects. These are preliminary planning estimates for a restricted service, not a promise of extreme-depth mastery, frontier-fleet experience or Staff readiness. Re-estimate openly when repository complexity or a failed gate changes the work. Gates determine readiness.

**VI:** Phạm vi đã tăng từ một capstone nhỏ sang service dài hạn có recovery và multiagent. Ước lượng cần tăng tương ứng. Nếu gate lỗi thì thu hẹp workload hoặc sửa boundary; không ghi “production-ready” chỉ vì hết số tuần.

## Design review before implementation

The October10 [bounded audit repair gate](../research/codebase-refactor-spec-2026-10-10.md) strengthens existing M0–M3/M6 evidence before any new NVIDIA execution component. It does not add a milestone. Continue from [verified coverage](08-implementation-coverage.md). The [bounded shared adapter](../research/failure-regression-spec-2026-10-10.md) now supplies the first evidence-to-regression slice within M0/M6; broader fresh-fix/reproduction gates remain. [Deterministic accepted context projection](../research/context-offloading-spec-2026-10-10.md) now supplies a bounded M5 source slice with dispatch/retrieval/recovery tests; semantic retention and the full long-duration M5 gate remain pending. NV-S1 boundary design can proceed independently. Required hackathon delivery keeps priority.

Use the engineering cycle **inspect source/evidence → specify purpose/owners/invariants → review → build the bounded component → inject faults → measure**. The human mastery cycle is **predict → trace code/data → explain → debug → transfer**, using the delivered implementation or a disposable copy. H8 oracle/failure-classification concepts inform M0; experimental methods inform M6. H11 single-worker ownership informs M3; H10 applies it to multiple workers in M4. Module numbers organize concepts, not a requirement to postpone necessary fundamentals or a circular dependency. No full H-module needs repeating when its evidence already exists.

**VI:** Thiết kế cần cơ sở đúng lúc: M0 cần oracle, M3 cần lease/fencing, M6 cần thống kê. AI phải giải thích và kiểm contract trước khi implement; không bắt Huy hoàn thành mastery trước khi reference được xây.

Keep one review record in the existing session/evidence record, tagged `D0`–`D7` and `C1`–`C6`. It contains: problem and scope; actors/state owners; typed inputs/outputs and identities; invariants; normal and failure sequence; quantitative resource/deadline assumptions with units; smallest falsifying experiment and oracle; rejected alternative with reason; open decisions, reviewer, disposition and evidence links. Refer to the canonical contracts rather than copying them into a new specification. Classify each review finding as unresolved, addressed or accepted within an explicit scope. AI review can identify defects; attribute it and keep human prediction/teach-back separate.

A design review passes only when its technical assumptions and inspected evidence are linked, the selected behavior answers its counterexample, contradictory contracts and blocking unknowns are resolved, and planned checks have an observable pass/fail outcome. Record unmeasured parameters as proposed, never as achieved. A design passing review permits the next authorized implementation slice; it proves neither human mastery, operational readiness nor a hiring outcome. Human prediction and teach-back are assessed separately under D012.

**VI:** Review không phải thêm thủ tục xin phép. Nó là cách tìm lỗi trên giấy khi sửa còn rẻ: ai có quyền commit, crash ở đâu thì biết gì, kết quả nào bác bỏ design? Tên reviewer và evidence phải có thật; agent không được tự điền rằng Huy đã giải thích được.

| Evidence layer | What establishes it | What remains unproven |
|---|---|---|
| Concept | Huy predicts, explains a state trace and transfers to an unfamiliar case | Actual implementation correctness, security and service reliability |
| Design | Reviewed interfaces, ownership, assumptions, failure cases and falsifying checks | Whether the implementation obeys them |
| Implementation | Deterministic tests and fault traces for a pinned build/environment | Live-model coding quality or reliability outside those cases |
| Research | Frozen task/run manifests, all outcomes, controlled intervention and uncertainty | Broader task populations, untested N or a universal scaling law |
| Operation | Restricted-canary traffic, observed SLI windows, recovery/rollback and explicit capacity | General availability, larger fleets or long-term reliability beyond observation |

**VI:** Một test pass chỉ chứng minh điều kiện test đó. Để nói service chạy được trong production, cần workload thật trong phạm vi khai báo, cửa sổ quan sát và cách khôi phục thực tế; diagram đẹp hoặc fixture không thay thế các evidence này.

## Milestones and required evidence

| Milestone | Curriculum | Additional effort | Deliverable and pass condition |
|---|---|---:|---|
| M0 Lock the task and oracle | H0, H8 | 4–6 h | Supported repo/base/environment selected; 6 calibration tasks; correct/no-op/known-wrong patches distinguishable |
| M1 Establish one-agent baseline | H1–H4; H8 outcome basics | 8–14 h | Typed loop, recorded stream replay, bounded tools, budget/stop states; every terminal result has evidence |
| M2 Build the execution boundary | H3, H7, H9 basics | 16–26 h | Task API, broker and disposable Linux worker; generated code cannot access control-plane secrets or grader authority |
| M3 Make execution recoverable | H4; H11 single-worker ownership | 12–22 h | Postgres/outbox/Temporal ownership; kill/retry/restart matrix passes, stale owners rejected |
| M4 Add bounded collaboration | H6, H10; H11 ownership; M2/M3 evidence | 18–30 h | Default two workers; validated research 1/2/4 profile admission; shared budget, physical limits and integration exercised |
| M5 Sustain long tasks | H5, H6, H11 | 12–22 h | Checkpoints, context rollover, evidence freshness, replanning; recover a multi-stage task across fresh environments |
| M6 Measure and optimize | H8, H13 service path | 22–38 h | Paired pilot, bounded scaling study, one fixed-N allocation intervention, workload replay and uncertainty analysis |
| M7 Operate a restricted canary | H11, H15 | 12–22 h | Release/rollback evidence, compact trace report, independent reproduction and unseen-fault research review |

All design reviews **D0–D7 are pending**; all milestone implementation gates remain **not demonstrated**. The existing offline lab is a prerequisite reference, not a completed M1 live-model baseline. M2 precedes arbitrary repository execution. M3 is tested with deterministic fixtures before provider calls obscure failures. Build the first independent verifier in M0 and keep strengthening it through all milestones.

**VI:** Có hai vòng test khác nhau: deterministic fixture để bắt lỗi hệ thống; model thật để đo khả năng làm task. Nếu trộn chúng ngay từ đầu, một lần fail sẽ không biết do model, tool hay recovery.

## M0 Define the problem before building orchestration

**D0 design review — pending; C4/C6.** Prerequisite learning: H0 state/evidence boundaries and H8's task, oracle, contamination and failure-classification basics. Specify the supported repository/base, task population, environment, protected grader identity and acceptance/review rule in the [system](01-system-specification.md) and [evaluation](03-evaluation-serving-and-efficiency.md) contracts (`EV-01`, `EV-04`). Predict how the same candidate is classified when tests are deleted, the tree changes or the environment cannot start. Exit from design: a six-case oracle truth table with reasons, explicit exclusions and no unresolved task identity. Production exit remains pending until M2 verifies grader isolation; trusted calibration alone cannot establish adversarial integrity.

**VI:** Trước orchestration, phải định nghĩa “đúng” theo yêu cầu nào và ai có quyền xác nhận. Nếu một patch sai được chấp nhận, tăng số agent chỉ khuếch đại số đo sai.

Select one supported Python repository and lock an immutable revision and reproducible environment. Provision the reference import-service task described in the [system specification](01-system-specification.md), or select an equivalent approved project with the same dependency/failure mechanisms. Record the choice; do not leave a mutable branch name as an experiment identity. Build six small calibration cases that exercise baseline failure, valid repair, invalid repair, deleted tests, stale artifact and environment failure. These calibrate the harness/grader and stay separate from the 36-task diagnostic pilot.

The task record contains user-visible requirements and a protected verification contract. The agent may add useful tests, but cannot redefine acceptance or weaken protected tests. Confirm the grading runner reads its completion receipt from a trusted channel tied to the candidate tree and grader identity. Save fixture preparation and all exclusions.

**Mastery:** explain how a process can exit with code zero without satisfying the task. Predict the result of changing the artifact after grading. **Exit artifact:** task manifest, environment lock and grader counterexamples. **Falsifier:** known-wrong code receives an accepted receipt.

**VI:** Oracle cũng là phần mềm có bug. Test nó bằng cả patch đúng và patch cố ý gian lận trước khi tin số success rate. Việc calibration tốt không có nghĩa bộ test đã bao phủ mọi hành vi thật.

## M1 Establish a traceable single-agent baseline

**D1 design review — pending; C1/C2.** Prerequisites: H1–H4 and H8's terminal-outcome distinctions. Design the typed event/state transitions, stream assembler, provider continuation boundary, action versus attempt identity, tool limits and reservation settlement in the [runtime contract](02-runtime-contracts-and-recovery.md) (`RT-04`–`RT-06`, `RT-10`). Predict a disconnect after a complete model action but before its result receipt. Exit from design: one full action trace and counterexample per dispatch/termination invariant, with retries classified by operation. Implementation exit begins with recorded responses on trusted fixtures; live-model execution waits for M2 and an explicit model/spend manifest. A working parser establishes neither task success nor safe arbitrary code execution.

**VI:** Byte đã nhận đủ khác với action đã được cấp quyền; action chạy xong khác với receipt đã commit. Design cần đặt tên từng boundary để retry không vô tình chạy lại effect.

Implement a provider-independent core with schema-checked calls, complete-stream assembly, bounded stdout/stderr capture, explicit finish reasons and total resource accounting. Start with scripted/recorded events and a trusted fixture. Add a real provider only after its task execution goes through M2's boundary; recorded response replay is sufficient for the first M1 gate. Pin model identifier, parameters, prompts and tool definitions. Record billed failed attempts rather than counting only successful replies.

Keep two adapters: the custom research harness and, later, a vendor SDK comparison when its tool access, verifier and budgets can be aligned. Do not claim a controlled harness comparison when the adapters use different tools or hidden resources. Make the comparison limitation visible.

**Mastery:** follow one incomplete argument buffer until it becomes an accepted call; identify the exact dispatch boundary. **Exit artifact:** event trace and baseline implementation with a terminal-state table. **Falsifier:** partial JSON executes, or a model's final prose bypasses verification.

**VI:** Baseline mạnh và đo được giúp biết thay đổi sau có ích hay không. Baseline cố tình yếu chỉ làm số cải thiện đẹp nhưng không giúp ra quyết định thực tế.

## M2 Establish isolation and external effect control

**D2 design review — pending; C1/C6.** Prerequisites: H3 process/file semantics, H7 authority/containment and H9 authentication/schema basics. Draw tenant → API → broker → sandbox → artifact/grader boundaries, including concrete identities, mounts, network routes, credentials and resource limits. Bind the design to `RT-01`, `RT-03`, `RT-07`, `RT-08` and serving `OP-01`/`OP-02`. Predict an artifact lookup using another tenant's identifier and a child process surviving its parent. Exit from design: every privileged transition has an owner, enforceable check and denial observation; Linux isolation mechanism and unresolved platform assumptions are explicit. Production exit requires actual enforcement/cleanup evidence on that deployment, not a threat-model assertion or prompt instruction.

**VI:** Quyền phải được kiểm tra ở nơi effect xảy ra. Identity trong log hữu ích để debug nhưng không tự chặn process đọc secret hoặc user tải artifact của người khác.

Implement API identity, repository authorization, artifact access checks, broker capabilities, and isolated execution. Repositories and tool outputs are untrusted inputs. Generated code receives a task workspace and explicitly allowed resources; provider credentials, workflow/database credentials and protected graders remain outside it. Limit CPU, memory, process count, disk, output, execution time and egress. Test actual enforcement. Document the Linux kernel/VM boundary and any host mounts or sockets.

Use separate worker identities for production-like execution and verification. Do not solve secret handling with prompt text or log redaction alone. A task that loses permission must be unable to create a newly accepted privileged effect. First product output is a review artifact; externally publishing a PR can be a later broker operation with a reconciliation contract.

**Mastery:** trace a malicious repository instruction to the exact denied capability. **Exit artifact:** threat model, enforcement evidence and resource-exhaustion results. **Falsifier:** candidate code can read a provider secret, modify a grader, or retrieve another tenant's artifact.

**VI:** Environment riêng cho worker giải quyết cả reproducibility lẫn security, nhưng hai tính chất này cần phép thử riêng. Một container chạy đúng dependency vẫn có thể mount nhầm home của host.

## M3 Establish durability and authoritative ownership

**D3 design review — pending; C2/C6.** Prerequisites: H4 crash windows and H11's single-worker transactions, outbox, lease, fencing and workflow-replay material; H10 is not required for this single-worker stage. Write the durable state/ownership table and normal, duplicate, partition and cancellation sequence for `RT-02`, `RT-04`, `RT-06`, `RT-10`–`RT-12`. Predict restart after an external effect with no receipt and after a committed outbox row with no workflow delivery. Exit from design: each crash window says what is known, who may act, what remains reserved and which observation can reconcile it. Production exit requires pinned-build fault/restore traces, including ambiguous states; automatic successful completion is not required where evidence is insufficient.

**VI:** Sau crash, có thể biết ít hơn thực tế đã xảy ra. Design đúng bảo toàn sự không chắc chắn đó; chỉ giải phóng liability khi có bằng chứng, không khi hết patience hoặc lease.

Implement task generation, per-node lease epoch, idempotency keys, event sequencing and atomic budget reservations in Postgres. Use an outbox to dispatch committed commands to Temporal. Keep workflow code deterministic and perform external work in activities. Define retry policy per action class, not globally. Continue long workflow histories at explicit boundaries with versioned restart references.

Exercise crashes before intent, after intent, after local effect, before receipt, after receipt, after candidate upload and during publication. On lease loss, stop the old process where possible and fence every authoritative acceptance path regardless. Preserve ambiguous external effects as `unknown` until operation-specific reconciliation resolves them. A new worker never blindly re-executes an uncertain mutation.

**Mastery:** draw a three-column database/workflow/execution timeline and place a crash between every pair of steps. **Exit artifact:** recovery matrix, duplicate-delivery evidence and stale-owner rejection. **Falsifier:** an old worker can advance current task state or release a potentially billed reservation.

**VI:** Recovery đúng không bắt buộc mọi tình huống đều tự hoàn tất. Đôi khi kết quả đúng là dừng ở `unknown` có bằng chứng rõ, thay vì tạo thêm side effect mà không biết.

## M4 Add two workers without losing ownership

**D4 design review — pending; C2/C3/C5.** Prerequisites: H6 evidence freshness, H10 DAG/critical-path mathematics, H11 ownership, and demonstrated M2/M3 implementation gates before multiworker effects. Specify node input/output/base versions, dependency validity, integration ownership, resource reservation and frozen profile admission (`RT-02`, `RT-03`, `RT-06`–`RT-08`; `EV-07`). Predict two independent edits that merge cleanly but violate an interface, then a partition retaining an obsolete sandbox. Exit from design: dependency/capacity diagrams, declared work/coordination assumptions and distinct production N=2 versus research N∈{1,2,4} contracts. Implementation exit repeats invariants at each enabled N. No measured scaling or additional production capacity follows from approving the graph.

**VI:** Dependency graph mô tả điều kiện cần để chạy; chưa chứng minh các task thực sự độc lập. Review phải tìm shared assumption và tài nguyên còn bị giữ sau partition trước khi cho thêm worker.

The coordinator emits a bounded dependency graph with input revisions, output contracts and node budgets. A worker claims a node under its own epoch; claiming another independent node must not revoke the first. Workspaces are independent. Integrate patches against exact bases through one owner; rerun verification on the resulting tree, even when each branch passed separately.

Test semantic conflicts, stale retrieval, changed API contracts, a failed dependency, duplicate handoffs, worker death and simultaneous budget reservations. Bound coordination messages and replans. The initial scheduler can be simple; fairness and quotas belong to declared load requirements. Fan out when useful work is independent and resources are available; otherwise run serially. Compare quality and elapsed time at aggregate resource ceilings.

Include a partition drill: the lease expires while the old sandbox's termination is unconfirmed. Its physical patch slot stays occupied; replacement admission must not exceed the two-sandbox limit. Model concurrency, runnable tools and retained sandboxes have separate counters. Logical reassignment does not prove the old process stopped.

After default-profile isolation/recovery passes, validate a separate frozen research profile with `patch_slot_limit` in {1, 2, 4}. Repeat admission, budget, partition and stale-result cases against that configured bound. The production profile stays at two. Scaling beyond demonstrated capacity is not an automatic next step. Use the [research contract](06-target-role-and-research-contract.md) to derive the experiment before implementation.

**VI:** Drill N=4 phải chứng minh cùng invariant trên capacity mới; lease expiry vẫn không giải phóng sandbox chưa biết đã chết hay chưa.

**Mastery:** explain a clean Git merge that creates a broken application. **Exit artifact:** multiagent trace plus single-agent comparison on calibration tasks. **Falsifier:** two agents jointly exceed the shared reservation ceiling, or integration trusts tests for a different tree.

**VI:** Parallelism giảm critical path chỉ khi không tạo thêm nhiều việc tích hợp. Một lần merge không conflict chỉ chứng minh Git ghép được text, không chứng minh các assumption tương thích.

## M5 Sustain progress across context and machine replacement

**D5 design review — pending; C2/C3.** Prerequisites: H5 context versus durable memory, H6 revision identity and H11 restart semantics. Design the restart manifest, artifact retention, context projection/probe, protocol-preservation and stale-evidence rules (`RT-07`, `RT-09`, `RT-10`). Predict a fresh environment receiving a summary written before the last accepted patch and a model switch with incompatible continuation state. Exit from design: a reader can derive the next safe action and every unresolved liability from persisted references; distinguish new model session from continuing an old protocol session. Production exit requires restoration on a genuinely fresh environment and the separate 24-hour durability drill. A short transcript or simulated clock jump cannot substitute for those observations.

**VI:** Checkpoint tốt phải phục hồi quyền quyết định và evidence, không chỉ file source. Nếu restart vẫn cần đọc trí nhớ của process cũ thì durability boundary chưa hoàn chỉnh.

Persist a restart manifest containing task/DAG version, accepted event offset, base and checkpoint tree identities, environment recipe, unresolved actions, budget liability, constraints, decisions with evidence, and next executable nodes. Reconstruct context from these records. Summaries are fallible projections: preserve source pointers and probe essential requirements after compaction. Revalidate changed evidence before using it to edit code.

Complete a staged multi-hour exercise with multiple context windows and at least one fresh environment. Then schedule a separate 24-hour interruption/recovery exercise, explicitly reporting active work versus idle elapsed time. This is a durability-only drill with its own manifest/deadline; exclude it from the T3 180-minute capability score rather than extending a timed-out task. Restore local progress using tracked artifacts; remote effects require their own receipts. Verify that context rollover and provider/model changes respect protocol contracts and invalidate incompatible caches or continuation state.

**Mastery:** reconstruct the next safe task action from the restart manifest without reading the old transcript; explain when a fresh provider session is valid and when continuing the original session requires its preserved protocol history and opaque response items. **Exit artifact:** pre/post-restart manifest, restored-tree comparison and constraint probes. **Falsifier:** a summary silently drops a user constraint and the release gate still accepts a violating patch.

**VI:** Memory tốt không phải nhét toàn bộ history vào prompt. Nó là giữ đủ thông tin đúng để quyết định bước tiếp theo, đồng thời có đường quay về bằng chứng gốc khi nghi ngờ.

## M6 Optimize the measured bottleneck

**D6 design review — pending; C4/C5/C6.** Prerequisites: full H8 causal comparison/uncertainty, H10 scaling assumptions and H13's API-backed critical-path profiling; H12 only for claims about inference internals. Freeze the task/run manifests, arm identities, resource envelopes, randomization/blocking, endpoints, exclusion/retry rules, clustering, stopping and held-out plan (`EV-01`–`EV-08`; `OP-03`/`OP-04`). Predict the curve and a result that would reject the chosen explanation before seeing results. Exit from design: the analysis can classify every possible terminal attempt and attribute a controlled intervention, with sample size justified for the declared diagnostic scope. Research exit requires raw runs and uncertainty; production-performance claims additionally require the observed workload/window. Hypotheses and plots of synthetic data are not measured gains.

**VI:** M6 bắt đầu bằng quyết định cần đưa ra, rồi chọn phép đo đủ để kiểm tra. Nếu đổi model, budget và scheduler cùng lúc, kết quả không thể trả lời nguyên nhân gain dù biểu đồ đẹp.

Follow the [evaluation contract](03-evaluation-serving-and-efficiency.md). Run a diagnostic pilot with independent tasks and paired arms; report all attempts, including failures and timeouts. Replay realistic arrivals, long tool waits, rate limits, cache misses and cancellations. Separate task queue time, environment startup, client-observed model TTFT/stream time, tool execution, integration and verification. Provider-internal queueing, prefill and decode compute remain unavailable or explicitly estimated unless exposed; self-hosted engine instrumentation can measure them separately. Keep aggregate dollars per accepted task alongside completion probability and time-to-verified-patch.

Choose one intervention from the ranked ablations. A useful first hypothesis is: “On tasks with independent implementation branches, bounded fan-out reduces time to verified completion without reducing acceptance at fixed total resource ceilings.” State strata and budgets before running. If conflicts or duplicate context dominate, the result may favor the single-agent baseline. Preserve that finding.

For the selected Multi-Agent Scaling target, make that hypothesis the main research thread: a 1/2/4-worker comparison, followed by static versus progress-aware allocation at one fixed N. Fit the intervention inside the same runner, budget ledger and task registry. Choose policies on research-development data, then use held-out confirmation; three worker counts do not establish a broad scaling law. Produce a compact critical-path/ownership/evidence view from existing traces.

**VI:** Tách hai experiment để biết gain đến từ fan-out hay allocation. Một kết quả âm rõ nguyên nhân vẫn hoàn thành research gate nếu phép đo và kết luận đáng tin.

**Mastery:** derive why halving model latency produces little gain when tests dominate wall time. **Exit artifact:** raw run table, completion/cost curves, uncertainty analysis and one controlled comparison. **Falsifier:** the claimed benefit disappears when failed runs and coordination tokens are counted.

**VI:** Tối ưu chỉ đáng giữ khi nó cải thiện metric mà người dùng cần trên workload đã định nghĩa. Cache hit cao hoặc token/s cao không đủ nếu thời gian nhận patch đúng tăng lên.

## M7 Operate within a demonstrated scope

**D7 design review — pending; C2/C4/C6.** Prerequisites: H11 operation/recovery, H13 queue/latency diagnosis and H15 research communication; prior implementation/research evidence must exist. Design the restricted tenant/repository/workload envelope, canary entry/exit, SLIs/observation windows, incident ownership, drain/cancel semantics, active-run compatibility, joint restore and rollback (`OP-01`–`OP-08`; `EV-08`). Predict rollback during an in-flight old-version task and restore with a missing artifact. Exit from design: every release decision has an observable trigger, action, owner and recovery check; the independent reproduction procedure can run from a frozen manifest. Operational exit requires observed canary/restore evidence and an actual independent reviewer; all remain pending until performed. Completion is assessed within the demonstrated scope.

**VI:** Runbook phải trả lời ai làm gì khi tín hiệu nào xuất hiện và dùng evidence gì để biết đã phục hồi. Review giả lập giúp chuẩn bị; chỉ traffic và diễn tập thật mới tạo operating record.

Assemble release evidence, pin active-run behavior, test database/artifact restore together, and demonstrate a rollback with in-flight tasks. Begin with trusted-team canary traffic on allowlisted repositories. Verify overload rejection versus accepted-work durability, cancellation, expired authorization and artifact retention. Keep one runbook per actionable failure: provider outage, stuck task, uncertain effect, worker loss, grader outage, growing queue and storage restore.

Distinguish stopping admission, draining tasks, cancelling execution and revoking publication; they have different consequences. Rollback of service code cannot undo an external effect. A failed security or stale-result gate blocks broad exposure even if average benchmark quality is high. Graduation is a tested operating envelope and explicit unsupported cases, not an unrestricted production claim.

**Mastery:** give a 20-minute architecture review, debug an unseen fault from traces, and implement one unfamiliar requirement without breaking the ownership model. **Exit artifact:** release packet and defended quality/cost decision. **Falsifier:** rollout changes active workflow semantics without compatibility handling, or restore loses accepted artifact/receipt relationships.

The [offline release contract](../research/offline-release-spec-2026-10-10.md) supplies a bounded M7 packaging/reproduction result on this machine. Fresh-machine, canary, rollback, long-duration and human-review gates remain separate. The later M5 skills dependency chain is capture(step2) → broker receipts(step3) → [accepted request disclosure(step4)](../research/skills-disclosure-spec-2026-10-11.md), each with separate [coverage](08-implementation-coverage.md). Step4 adds exact scripted/native mock requests, historical retry checks and source-state resource authorization. Step5 typed post-turn checkpoint/fresh-owner recovery is now implemented under [its frozen contract](../research/skills-recovery-spec-2026-10-11.md). No milestone is added; the current candidate has separate installed acceptance while historical releases stay immutable. Human mastery remains separate.

Extend this review to one research conclusion and one independent reproduction of a frozen experiment. The reviewer must reconstruct the outcome from manifests/raw evidence; Huy must diagnose a new fault and defend or revise the conclusion. Mark independent reproduction pending when no reviewer has actually performed it. This is portfolio evidence, not an automatic Staff-level hiring assessment.

**VI:** Độc lập nghĩa là người khác thực sự rerun hoặc kiểm evidence; không phải agent tự tạo một lời khen thay peer review.

**VI:** Vận hành là biết phải làm gì khi mọi thứ không như demo. Một runbook tốt chỉ ra tín hiệu, nguyên nhân có thể, bước kiểm chứng, hành động và điều kiện xác nhận đã phục hồi.

## Original delivery mapping and current extension order

The table preserves the original delivery decomposition; many components now exist. Check [08](08-implementation-coverage.md) before starting an item and reuse implemented primitives and evidence. Start an extension after its relevant engineering design review; human mastery is not a delivery gate. Execute in dependency order and parallelize bounded independent work once contracts agree. Record a failed gate as pending work, not as a reason to expand the architecture.

| Order | Work item | Acceptance evidence |
|---:|---|---|
| 1 | Select repository/base, six calibration cases and protected grader | Correct patch accepted; no-op/wrong/stale/environment cases classified |
| 2 | Define task/node/action/candidate/verification schemas | Invalid states rejected; identity relationships traceable |
| 3 | Record/replay a provider stream and complete tool calls | Fragmented/reordered-invalid inputs never cause early dispatch |
| 4 | API submission and tenant-scoped idempotency | Duplicate request same payload reuses identity; changed payload conflicts |
| 5 | Isolated workspace and broker with bounded I/O | Enforcement and process cleanup tests pass |
| 6 | Durable action intent, receipts and budget liability | Crash ambiguity retained; billed attempts reconcile |
| 7 | Per-node claim/heartbeat/fence and outbox workflow bridge | Duplicate dispatch safe; stale result rejected |
| 8 | Fresh verifier and immutable artifact delivery | Receipt binds exact candidate/grader/environment |
| 9 | Coordinator, two workers and serialized integration | Independent ownership, conflict/rebase and reverify exercised |
| 10 | Restart manifest, context projection and constraint probes | Resume on fresh machine with no lost unresolved actions |
| 11 | Paired quality and workload replay runner | All resource use and censored runs accounted for |
| 12 | Load/chaos, restore/rollback and canary runbooks | Release gates from the evaluation contract demonstrated |

**VI:** Có thể giao AI agents làm nhiều item song song, nhưng phải có một người tích hợp và một contract chung. Huy nên chọn một invariant để dự đoán và kiểm chứng mỗi buổi, thay vì cố đọc mọi dòng của tất cả nhánh cùng lúc.

## Research depth after the core service

For authorized NVIDIA implementation follow [NV-S0–NV-S4](07-reference-implementation-spec.md#ordered-implementation-slices): CPU numerical reference and negative controls first; shared failure-evidence adapters and GPU boundary design next; then isolated GPU execution, the agent loop, one knowledge/profiler intervention and reviewed data/use evidence. Parallelize only independent bounded work. The first slice is confined to the compute workbench/tests and cannot change the hackathon runtime or claim a CUDA result. Engineering review and source/test evidence precede promotion; Huy's learning remains H0 until his session evidence advances it.

The [NVIDIA role refinement](06-target-role-and-research-contract.md#9-nvidia-coding-tools-evidence-within-the-same-project) adds NV1–NV3 inside existing milestones: GPU build/isolation recipe at M2, knowledge/skill/tool identities at M5, correctness/performance and data-lineage evidence at M6, actual use/reproduction at M7. Freeze one workload and hardware boundary before implementation; no new milestone, scheduler or benchmark engine. Required hackathon delivery keeps priority. The existing hour ranges exclude this later specialization; scope and estimate it after the selected workload/toolchain design. Training and self-hosted inference are separate conditional experiments, not prerequisites for an API-driven agent optimizing GPU code.

The [2026-10-10 course audit](../research/course-audit-2026-10-10.md) refines existing items 5, 10 and 11 through [four extension contracts](07-reference-implementation-spec.md#course-derived-extension-contracts--proposed-2026-10-10). Start with a bounded evidence/regression adapter using existing controls; then accepted deterministic projections and accounted summaries (M5), immutable skills through the broker (M2/M5), and one supervised LSP profile (M2/M5). Skills may proceed alongside context after shared identities agree; LSP requires its process-lifetime boundary first. Add one-variable development comparisons to M6 without another pilot, task population or research thread. The initial documentation update did not implement those extensions. Subsequent failure-evidence, deterministic context, immutable capture, broker loading and accepted disclosure deliveries have their own source-bound records in [coverage](08-implementation-coverage.md); skills-aware fresh-owner recovery is now delivered under its bounded typed checkpoint contract, while LSP and accounted semantic summaries remain pending. Preliminary hour ranges above are not newly validated estimates; re-estimate the selected slice after its implementation design and measured integration effort.

**VI:** Course làm rõ các phần còn thiếu, không quay về build lại loop, queue, verifier hoặc evaluator. Scope mới nằm trong gap đã ghi; nếu effort thực tế tăng, cập nhật estimate minh bạch thay vì giấu thêm một project trong plan.

H12 supplies the token/tensor/KV path behind model latency; H13 can first profile an API-backed workload without running a GPU. Add self-hosted inference only after capturing representative traces. Pin one model and engine, establish quality parity, measure memory and queue behavior, then study batching, prefix caching, eviction and routing. H14 begins with offline trajectory validation; training is a separate experiment with data rights, exact token/action masks, held-out evaluation and a declared compute budget.

The primary research result is the controlled scaling/allocation study in the [role contract](06-target-role-and-research-contract.md). Context projection, recovery, decomposition or serving changes are targeted causal ablations only when its traces justify them. A clean negative result that identifies the limiting factor can satisfy the research gate. Do not start a second research program merely to make the portfolio broader.

**VI:** Đi sâu tới tensor/kernel khi nó trả lời câu hỏi đang đo. Với capstone này, mastery trước tiên là từ yêu cầu của user đến patch đúng qua mọi failure boundary; inference và RL mở rộng chiều sâu sau đó.


## Current bounded readiness delivery — 2026-10-11

The [current dependency/evidence plan](../research/system-readiness-plan-2026-10-11.md) adds typed skills post-turn recovery (M5/RT-09), persisted atomic pending-task caps and configured loopback fixture serving (M7/SYS-08/OP admission), durable per-instance local-Docker cleanup (M3/RT physical-slot ownership), and trusted RMSNorm qualification preparation (H12/NV-S1 partial). The [coverage register](08-implementation-coverage.md) owns implementation status and open gates; these additions do not replace the broader requirements above.

A restored checkpoint supplies data, a fresh claim supplies authority, a terminal container observation permits physical-slot release, and a verification receipt permits candidate evaluation. None substitutes for the others. The service currently runs fixed authored fixtures; a real live repair service still needs the separately frozen workload/provider/operation envelope. GPU preparation runs no generated code and defaults to no execution. Paid execution and human mastery remain unchanged.

**VI:** Ta hoàn thành các boundary nhỏ có thể kiểm chứng và giữ nguyên production contract. Đừng suy “cleanup xong” thành “task được retry”, hoặc “HTTP trả200” thành “service đạt SLO”.
