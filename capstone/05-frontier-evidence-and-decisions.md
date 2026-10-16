# 05 — Frontier evidence and capstone decisions

**Evidence checked: 2026-10-08, Asia/Ho_Chi_Minh.** This chapter turns public engineering evidence into decisions for one durable, long-horizon coding service. It builds on the existing [product audit](../research/claude-code-cursor-evidence-2026-10-08.md), [serving audit](../research/serving-evaluation-training-audit-2026-10-08.md), and [architecture reference](../docs/03-production-architecture-and-stack.md). The primary pages below were reopened for this chapter. Publication dates are stated where available; undated documentation is a live contract checked today, not a historical snapshot.

**VI:** Tài liệu này chọn cơ chế cần xây và lỗi cần chứng minh đã xử lý. Nó không suy đoán source code nội bộ, cũng không biến số liệu hãng công bố thành kết quả của capstone.

**Evidence labels:** *documented* means a public interface describes behavior; *reported* means its authors describe an experiment or deployment; *proposed* means our engineering choice; *measured* requires a saved local run. Every decision below is proposed until its test passes. No paid inference, cloud deployment, or vendor-result reproduction occurred in this research step.

The later [October 10 NVIDIA audit](../research/nvidia-role-alignment-2026-10-10.md) supplies role/tool evidence for the [ordered implementation slices](07-reference-implementation-spec.md#ordered-implementation-slices). It does not redetermine the dates or reproduce the vendor results below. NV-S0 first establishes numerical semantics; GPU and production claims require their own subsequent evidence.

**VI:** Một service chạy lâu chưa chắc bền: có thể chỉ chưa gặp lỗi. Bằng chứng quan trọng là giết worker đúng thời điểm nguy hiểm rồi quan sát task, effect và artifact được phục hồi thế nào.

## 1. Separate task lifetime from worker and sandbox lifetime

**Source and scope.** Anthropic's [Managed Agents engineering article](https://www.anthropic.com/engineering/managed-agents), **2026-04-08**, reports separating durable session history, harness execution, and sandboxes. A replacement harness reads existing events; a failed execution environment can surface as a tool error. This supports interface separation, not a claim that all Claude Code products share that topology.

**Decision.** Give tasks, attempts, workspaces and artifacts distinct identities. Keep task intent and events outside workers. Rebuild a worker from recorded state; reconstruct an execution environment from an image digest, repository base and artifact manifest. Cache loss must affect performance rather than correctness. A Git commit is a content checkpoint, not a snapshot of every running process or external side effect.

**Failure/test.** Kill the sandbox while its parent is waiting. Kill the parent while the sandbox is alive. Require explicit outcomes for both, preserved task ownership and no invented completion. A new worker must restore the correct artifact version.

**VI:** Đừng gắn “task đang tồn tại” với một PID. VM sống nhưng lease đã mất cũng có thể là worker cũ nguy hiểm; task còn nhưng VM chết phải khôi phục được từ bằng chứng.

## 2. Durable orchestration needs explicit retry boundaries

**Source and scope.** Cursor's [cloud-agent lessons](https://cursor.com/blog/cloud-agent-lessons), **2026-06-02**, reports adopting Temporal, separating loop/machine/conversation state, and replacing perpetual workflows with shorter task workflows. Its streaming layer can replace partial output after an attempt retries. Reported fleet scale is not our capacity target.

**Decision.** Run nondeterministic model and tool calls as activities outside deterministic workflow replay. Distinguish operation ID from attempt ID. Persist intent before dispatch and receipt after completion. Use idempotency or operation-specific reconciliation for mutations; an acknowledged workflow retry does not imply exactly-once effects. Keep provisional stream events separate from committed observations. Bound workflow histories and version active executions deliberately.

**Failure/test.** Crash after creating a remote artifact but before saving its receipt. The next attempt must discover the existing effect or enter `UNKNOWN`; it must not blindly create another. Disconnect during streamed output and verify the UI replaces the abandoned attempt rather than concatenating it.

**VI:** Temporal nhớ quá trình điều phối, không tự tạo transaction chung với GitHub. Retry đúng ở tầng workflow vẫn có thể lặp effect nếu tool không có khóa idempotency hoặc cách đối soát.

## 3. Delegate ownership, then measure whether parallelism helps

**Source and scope.** Cursor's [swarm research](https://cursor.com/blog/agent-swarm-model-economics), **2026-07-20**, reports planner/worker decomposition, explicit ownership of design questions, shared design records and neutral conflict resolution. Its solo runs were graded informally: the post does not establish a controlled universal advantage over single agents. [Projects](https://cursor.com/blog/projects), **2026-09-10**, describes a coordinator, shared context and event subscriptions as product capabilities, not a public implementation specification.

**Decision.** Begin with a coordinator and at most two coding workers. Each work item names its owner, dependencies, base revision, artifact contract and acceptance criteria. Use isolated branches and a serialized integration queue. The coordinator owns cross-cutting design choices; workers propose changes to those choices rather than independently redefining them. Keep single-agent execution as the baseline.

**Failure/test.** Give two workers incompatible interface assumptions, duplicate a completion event and cancel a parent. Verify decision conflicts are surfaced and children obey the configured cancellation policy. Compare accepted tasks per dollar and wall time under matched budgets.

**VI:** Chia file chưa chắc chia được quyết định kiến trúc. Hai worker có thể sửa file khác nhau mà vẫn tạo hai định nghĩa mâu thuẫn cho cùng API. Ownership cần bao gồm ý nghĩa, không chỉ đường dẫn.

## 4. A separate context is useful; it is not a security boundary

**Source and scope.** Current [Claude Code subagent docs](https://code.claude.com/docs/en/sub-agents) document configurable tools, separate subagent context and optional worktree isolation. [Agent-team docs](https://code.claude.com/docs/en/agent-teams), **live, checked 2026-10-08**, warn of coordination overhead, additional tokens and same-file conflicts; sequential or tightly coupled work can favor one session. Exact defaults are version-sensitive.

**Decision.** Pass each child a bounded task packet: current decision IDs, relevant paths, base hash, permissions, budget reservation and required outputs. Return structured findings plus artifact references. Do not copy full transcripts by default. Enforce capabilities in the tool broker; do not assume a role prompt, worktree or child report creates trust. Preserve the origin of untrusted information when it travels through a child.

**Failure/test.** Place an instruction to exfiltrate secrets in a tool result, then have a child summarize it. The summary must not acquire permission to execute it. Test two simultaneous budget reservations against the same parent balance.

**VI:** Subagent giảm nhiễu trong context nhưng vẫn có thể mang prompt injection về cho cha. “Agent của mình nói” không làm nguồn ban đầu đáng tin hơn; quyền phải được kiểm tra ngoài model.

## 5. Long-horizon progress requires durable acceptance state

**Source and scope.** Anthropic's [long-running harness article](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), **2025-11-26**, describes initializer and coding-agent roles, incremental work and handoff artifacts. It reports that compaction alone did not prevent incomplete implementations or premature completion in that setting. This older mechanism remains relevant; its original model-specific prescriptions should be re-evaluated.

The later [application-development harness report](https://www.anthropic.com/engineering/harness-design-long-running-apps), **2026-03-24**, describes planner/generator/evaluator roles and negotiated acceptance contracts. It subsequently removes sprint scaffolding for a stronger model. Its solo/full examples differ in runtime, spend and expanded scope; they do not isolate a causal multiagent benefit. Keep testable acceptance contracts while ablating how frequently a separate evaluator runs.

**VI:** Giữ tiêu chuẩn “done” ổn định; kiểm định lại nhịp chia sprint và QA khi đổi model. Cấu trúc từng hữu ích có thể trở thành overhead.

**Decision.** Store a versioned requirement checklist, environment recipe, known failures and evidence links outside model context. A session starts by checking the current repository and outstanding requirements, not trusting the last summary. Completion requires a verifier result bound to the exact candidate and acceptance version. Use summaries as indexes to durable evidence, never as the only evidence.

**Failure/test.** Force three context resets while one deferred requirement remains unsatisfied. Require the resumed agent to identify it. Replay a previously passing test receipt after a new edit; completion must remain unverified until the current candidate is checked.

**VI:** Ghi “đã xong” vào progress file chỉ là phát biểu. Bằng chứng cần chỉ rõ đã test commit nào, bằng grader nào, trên yêu cầu phiên bản nào. Nhờ vậy đổi context không đổi tiêu chuẩn hoàn thành.

## 6. Preserve provider state and treat compaction as a transaction

**Source and scope.** Claude's [preserved-thinking contract](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking), **live, checked 2026-10-08**, describes model and prefix compatibility, account-dependent enforcement and supported transformation exceptions. Prefix enforcement defaults apply to affected models on accounts created from **2026-08-31**; older accounts can opt in. Visible text alone is insufficient for faithful replay.

**Decision.** Persist opaque response items using the provider's supported serialization. Freeze each session's adapter and prompt versions. Keep a raw event log and a separately versioned context projection. Record a compaction boundary, source event range, generated summary and retained items before activating the replacement context. Never assume the same rewrite is valid across providers.

**Failure/test.** Restart after receiving opaque items; change one earlier tool result; switch models; interrupt compaction before commit. Compare requests and provider diagnostics. No half-activated summary or silent loss of required state may be treated as successful continuation.

**VI:** Context là view được dựng từ lịch sử, không phải lịch sử duy nhất. Compaction cũng có trạng thái trước/sau; nếu crash giữa chừng, phải chọn được một phiên bản nhất quán để tiếp tục.

## 7. Put credentials and policy outside generated-code execution

**Source and scope.** Anthropic's [containment account](https://www.anthropic.com/engineering/how-we-contain-claude), **2026-05-25**, describes failures involving pre-trust configuration and exfiltration through an allowed destination. It argues for environmental containment and credential boundaries. It does not promise that a classifier or sandbox eliminates every failure.

**Decision.** Separate the execution environment from the control plane and verifier. Keep broad provider/repository credentials in a broker. Grant narrow task capabilities, enforce filesystem/network/resource policy outside generated code, and recheck authority at sensitive effect boundaries. Explicitly control startup hooks and repository configuration before executing them. Terminate process trees, not just the shell parent.

**Failure/test.** Test denied mounts, symlink escape, forbidden egress, resource exhaustion and background descendants. Include an allowed-domain request using the wrong account identity. Confirm revocation prevents new broker actions while already-issued effects receive explicit reconciliation.

**VI:** Domain đúng chưa đủ: cùng một API có thể upload dữ liệu vào tài khoản kẻ khác. Cần kiểm tra cả identity, operation và dữ liệu; không đưa secret vào sandbox rồi hy vọng log redaction sẽ bảo vệ nó.

## 8. Evaluate the complete system under sealed conditions

**Source and scope.** Cursor's [coding-benchmark audit](https://cursor.com/blog/reward-hacking-coding-benchmarks), **2026-06-25**, reports substantial score drops after sealing future Git history and restricting network access. This establishes that evaluation environment policy can change measured success. The reported audit is not an independent result for our service.

**Decision.** Pin task, base commit, environment, model, harness, tool schemas and grader. Separate developer feedback tests from protected acceptance checks. Apply candidate patches to clean verifier environments and bind results to candidate hashes. Audit transcripts for answer retrieval and test manipulation. Report unresolved tasks and failures, not only successful trajectories; compare single-agent and delegated configurations on paired tasks.

**Failure/test.** Seed a future-fix commit, an answer URL and a forged success message. Verify the sealed suite blocks the answer channels and ignores claimed completion. Intentionally terminate a test process before assertions: zero exit alone must not count as verifier completion.

**VI:** Benchmark đo cả model, harness và quyền truy cập. Nếu agent đọc được lời giải trong lịch sử Git, điểm cao không chứng minh nó suy ra bản sửa. Grader cũng là một hệ thống có thể bị đánh lừa.

## 9. Optimize verified throughput, not cache percentage alone

**Source and scope.** Cursor's [efficiency report](https://cursor.com/blog/improved-token-efficiency), **2026-09-23**, reports reducing token costs by 7% through several context changes. It is a combined production observation, not a promised benefit for each mechanism. [vLLM APC documentation](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/), page date **2026-09-20**, explains shared-prefix reuse and its prefill-only benefit; decode remains work.

**Decision.** Render stable instructions and tool definitions consistently; load infrequent schemas on demand where the provider supports it. Bound observations and save full outputs as artifacts. Instrument our queues, client-observed TTFT/stream timing, provider-reported cache usage, tools and verification. Isolate prefill/decode compute only when provider telemetry or a self-hosted engine exposes it. Start with hosted inference; evaluate self-hosting only against an explicit quality and cost objective using recorded arrival times, idle gaps and contexts.

**Failure/test.** Replay identical tasks with tail appends versus early prompt edits, warm versus expired cache and one versus multiple workers. Record dollars per verified resolution, p95 latency and failures. Reject an optimization that raises cache hits while worsening completion quality or tail latency.

**VI:** Build chậm có thể chi phối toàn bộ task dù cache rất tốt. Cache làm giảm prefill lặp lại; nó không xóa chi phí đọc context ở decode hay thời gian chạy test. Đo critical path trước khi tối ưu.

## 10. Use an open implementation as a falsifiable comparator

**Source and scope.** The [OpenHands SDK paper v2](https://arxiv.org/abs/2511.03690v2), **2026-04-22**, describes a modular SDK and deployment evidence. Its [persistence docs](https://docs.openhands.dev/sdk/guides/convo-persistence), **live, checked 2026-10-08**, separate base state from event files and show restoration by conversation ID. These are inspectable reference mechanisms, not proof of our recovery guarantees.

**Decision.** Pin an OpenHands SDK revision for a narrow comparison: tool schema, persisted event, restored conversation and execution boundary. Reproduce one task under our harness and the reference with the same model, environment and budget. Keep the existing tiny lab as the simplest semantic reference. Do not import an entire framework solely to inherit the label “production.”

**Failure/test.** Crash at matching boundaries in both systems; inspect what is restored, omitted or uncertain. Verify persistence configuration does not expose credentials to the agent workspace. Record differences rather than assuming similar APIs imply identical semantics.

**VI:** Reference code hữu ích vì có thể kiểm tra và phản bác. Khi hai harness xử lý cùng lỗi khác nhau, hãy truy ra contract nào khác—đừng quy mọi khác biệt cho model.

## Evidence gate for the capstone

Maintain a decision ledger containing source/version, hypothesis, test, observed result and remaining limitation. First prove one complete task survives process loss and context reset while preserving authority and verifiable artifacts. Then add bounded delegation and compare it with that baseline. Only after the same semantics survive concurrent load should the service claim fleet reliability. Public sources support these directions; private model internals, vendor scheduling algorithms and product-scale reliability remain outside the evidence available here.

**VI:** Bài teach-back: effect đã xảy ra nhưng receipt chưa lưu, verifier cũ vẫn pass, worker mới đã nhận lease—thành phần nào có quyền làm gì? Vẽ timeline rồi chỉ ra bằng chứng cần có trước khi hệ thống được phép tuyên bố hoàn thành.
