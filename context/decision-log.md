# Durable project decisions

Updated: **2026-10-16**. Historical decision dates remain unchanged.

Record a decision when it changes future behavior. Keep date, source/owner, reason, status and links; supersede old decisions explicitly. Design choices remain proposed until tested.

**VI:** Log này giữ “vì sao chọn” và “khi nào cần xem lại”, không chứa mọi câu trong chat. Nó giúp tránh model mới coi một phương án đang nghiên cứu là sự thật đã xác minh.

| ID | Date | Decision and owner | Status / reconsideration |
|---|---|---|---|
| D001 | 2026-10-08 | Huy requests learning the relevant mechanism before building it | Superseded by D012 for implementation sequence; retained as historical preference |
| D002 | 2026-10-08 | Use H0–H15 as the concept sequence and the eight capstone milestones as implementation mapping | Active organization; update mapping rather than creating another curriculum |
| D003 | 2026-10-08 | Begin with H0 state/effect/verification boundaries using the existing trusted lab | Prepared learning choice; no mastery claimed |
| D004 | 2026-10-08 | Keep compact agent rules, current state, selected study packets and source evidence separately | Workspace design; revise if context proves missing or redundant |
| D005 | 2026-10-08 | API inference, bounded workers and independent verification are the proposed first capstone path | Proposed engineering choice from [specification](../capstone/01-system-specification.md); test at the relevant gates |
| D006 | 2026-10-08 | User-authorized selection: Anthropic Staff Research Engineer, Multi-Agent Scaling; tied top checked salary band and strongest direct project fit | Active target, backed by [role contract](../capstone/06-target-role-and-research-contract.md); no automatic credential, tenure or hiring claim |
| D007 | 2026-10-08 | Add only bounded scaling, one allocation comparison and independently usable evidence inside existing milestones | Proposed scope; preserve production two-worker default, frozen gated research limit and learn-first workflow |
| D008 | 2026-10-08 | Huy requests detailed role-aligned engineering/research design before building; use SYS/RT/EV/OP requirements, existing H0–H15 and per-milestone design reviews | Sequence superseded by D012; evidence distinctions remain active |
| D009 | 2026-10-08 | Proposed execution cutoff uses the database clock at the final fenced eligibility write with trusted verification evidence already present; durable commit observation is recorded separately | Runtime design correction; requires race/failure tests at M3 and consistent evaluator scoring at M6 |
| D010 | 2026-10-08 | Initial 1/2/4-worker study establishes bounded evidence; larger-team ownership remains conditional expansion after canary evidence and measured bottleneck | Avoid unearned frontier-scale claims; scope and estimate expansion from observed capacity and authorized resource budget |
| D011 | 2026-10-08 | Proposed authority-database restore uses quarantine, old-actor fencing, fresh service incarnation, cursor reset and beyond-snapshot reconciliation; drain and execution quarantine remain distinct | Cross-review correction to runtime/operations contracts; requires F13 and restore evidence before operational claims |

**VI:** D001 là preference của Huy; D005 là thiết kế đề xuất. Hai loại này có cách thay đổi khác nhau: preference theo chỉ thị mới, thiết kế theo evidence và tradeoff được ghi lại.

## Implementation-first reference decision

| ID | Date | Decision and owner | Status / reconsideration |
|---|---|---|---|
| D012 | 2026-10-08 | Huy explicitly requests deep existing-document and primary-source audit, engineering specification, Astra architecture/review and 6.1 Sol implementation; build the codebase first, then master first principles through exact code/data/tensor traces | Active human preference; supersedes D001/D008 sequence and learn-first wording of D007. Human prediction/teach-back gates remain separate from delivery. Learning order and gates superseded by [D046](#d046-production-backward-learning-replaces-mastery-gates) on 2026-10-16; implementation authorization unchanged |
| D013 | 2026-10-08 | Shared SQLAlchemy state machine uses SQLite for inspectability and PostgreSQL with a coarse authority-row lock for the bounded reference | Implemented and concurrency tested; optimize only after a measured contention question. Not a frontier-throughput claim |
| D014 | 2026-10-08 | Use one frozen synthetic issue-tracker family, an explicit scripted baseline and external Linux RPC grading for mechanics tests | Implemented; 42 task definitions are variants across 13 templates, not independent or held-out capability evidence |
| D015 | 2026-10-08 | Preserve provider request/response artifacts; require trusted configured rate envelopes for live harness; keep paid inference and GPU performance separate | Mock-transport/CPU evidence exists. No live price, spend, accelerator or provider capability result invented |
| D016 | 2026-10-08 | Independent Astra review found and tested defects in effect/billing order, truthful deltas, provisioning uncertainty, controller fencing, outbox selection, token-bound replay and checkpoint causality | Repairs and regressions recorded in [review](../research/implementation-code-review-2026-10-08.md); broader production source gaps remain explicit |

**VI:** D012 là thay đổi có thẩm quyền từ Huy. Các lựa chọn D013–D016 là quyết định engineering có thể bị thay đổi bởi test hoặc phép đo tốt hơn; không tự biến thành bằng chứng em đã hiểu.

## Production audit decisions: 2026-10-09

| ID | Date | Decision and owner | Status / reconsideration |
|---|---|---|---|
| D017 | 2026-10-09 | Astra audit / Sol repair separates complete provider response retention, semantic acceptance and trustworthy usage settlement; duplicate effects require immutable durable result evidence; Temporal memo is awaited and stop survives activity/history boundaries | Focused regressions and local SDK replay; exact outcomes in [current verification](../research/production-review-verification-2026-10-09.json). No paid inference or automatic remote-effect reconciliation |
| D018 | 2026-10-09 | External verifier snapshots its input and latches transport failures outside candidate expected exceptions; container cleanup binds a creation nonce plus immutable instance ID | Audited repairs in [production code review](../research/production-code-review-2026-10-09.md); not a kernel escape or broad hostile-tenant safety claim |
| D019 | 2026-10-09 | Schema 2 hashes canonical tenant/logical-ID tuples; schema 1 requires explicit offline migration with quiesced writers, backup/copy validation and writer compatibility guards | [Migration contract](../service/migrations/002_identity-and-writer-protocol.md). No silent upgrade, mixed-version rolling migration, privileged-SQL isolation or recovery of already-lost aliases |
| D020 | 2026-10-09 | Local check timeout/interruption retires only its recorded POSIX group, monitoring beyond leader exit and escalating bounded signals | Launcher cleanup only; escaped groups and Windows job-object descendant retirement remain outside this guarantee |

**VI:** Những lựa chọn này giữ evidence không bị mất hoặc hiểu sai qua retry, parsing và cleanup. Chúng không chuyển source gap thành production feature đã xong. Schema/writer protocol là compatibility contract có giới hạn; secret, quyền SQL và environment fencing vẫn thuộc operator boundary riêng.

## D021 — Research observations retain consumption and actual cache residency (2026-10-09)

Evaluation revisions are cumulative for settled money, tokens, CPU and review time; reconciliation can reduce reserved/Unknown exposure without deleting consumption. Numeric contracts reject booleans, nonfinite values and derived service-time overflow. Serving replay reconstructs initial prompt + prior output + tool observation, subtracting only a currently resident initial prefix; it assumes no private pinned KV. Returned cache records cannot mutate ownership. CUDA samples release outputs and report starting allocated/reserved memory plus incremental peaks under a declared warm allocator policy; hardware validation remains pending. Distinguishing tests and the independent Astra re-review are recorded in the [production review](../research/production-code-review-2026-10-09.md).

**VI:** Báo cáo mới không được xóa tiền đã tiêu. Cache miss sau tool gap phải trả lại phần prefill bị mất; reset peak counter không giải phóng tensor hay bộ nhớ allocator. Những invariant này giữ số đo có nghĩa trước khi chạy GPU/model thật.

## Hackathon delivery profile

| ID | Date | Decision and owner | Status / reconsideration |
|---|---|---|---|
| D022 | 2026-10-10 | Huy requests NVIDIA x Nebius Coding-track analysis/design/delivery plan; team confirmed as one human + Codex GPT + Gemini. AI proposes small Python verified repair, one worker for this profile, API inference and conditional clean restart/matched pilot | [Hackathon packet](../hackathon/README.md); preserves existing capstone default and H0–H15. Four hours/day and Super selection are proposals; spend/access remain unresolved. Required repair/access/release take priority if Oct17 gate is missed |
| D023 | 2026-10-10 | Astra research/review and Sol implementation add native global-only Nebius protocol, exact request/provider/endpoint artifacts, raw-before-usage-before-semantics, nullable-field support, subset counters and no cache premium envelope | Implemented with mock regressions and independent review; [verification](../research/hackathon-2026-10-10/verification.json). No live NVIDIA capability, provider-bound rate-approval schema, retained HTTP error metadata or product completion implied |

**VI:** Quyết định D022 là cách đóng gói capstone cho deadline, không phải đổi curriculum hoặc chứng minh chiến thắng. D023 chứng minh protocol trên mock và lỗi review đã sửa; model thật, runner không đọc oracle và free judging access vẫn cần evidence riêng.

## D024 — Integrate course mechanisms through existing production contracts (2026-10-10)

Huy requests a deep course audit and useful integration, especially compaction, skills, LSP and evals. Three Astra source audits plus independent integration review inspected commit `4691f51e0f4977be0d3f0fc9a4667e75366f22ee`; [evidence](../research/course-audit-2026-10-10.md) and [selected licensed snapshot](https://github.com/decodingai-magazine/building-a-coding-agent-from-scratch-course/blob/4691f51e0f4977be0d3f0fc9a4667e75366f22ee/README.md) are retained. Adopt bounded mechanisms through [07's proposed extensions](../capstone/07-reference-implementation-spec.md#course-derived-extension-contracts--proposed-2026-10-10), preserving RuntimeStore authority, provider artifacts, cumulative/unknown billing, physical resource accounting, external verification, all-assigned outcomes and held-out lineage. Do not introduce course framework/vendor dependencies, another benchmark population or another curriculum. Correct stale milestone learn-first delivery gates under D012; human mastery stays separate.

Sequence within this extension work: local regression/evidence controls → deterministic accepted context projection → accounted semantic summaries; immutable skill activation can proceed after common identity contracts agree; LSP needs a supervised bidirectional lifetime and one pinned profile before enrichment. Native provider compaction, push diagnostics, broad server support and multiplexing are separate future decisions. This does not displace D022's deadline-critical delivery. Status: reviewed design, **not implemented or live-evaluated**. Reconsider a mechanism if measured quality/cost or its boundary tests fail; preserve the failure evidence rather than expanding scope automatically.

**VI:** Quyết định này dùng course để lấp gap cụ thể, không copy nguyên product. Summary, skill và LSP chỉ cung cấp context/evidence; không được tự cấp quyền hay quyết định completion. Audit không điền mastery cho Huy hoặc biến các gap thành feature đã có.

## D025 NVIDIA coding tools specialization within the existing project

**2026-10-10.** Huy requests current NVIDIA senior/principal role research, first-principles decomposition and minimal justified plan updates. Three Astra research/source-review branches support the [audit](../research/nvidia-role-alignment-2026-10-10.md). Select **Senior Research Engineer — AI Coding Tools, JR2017020, advertised Level 6** as the NVIDIA target: directly relevant coding research and the same highest checked close-role base ceiling as two principal alternatives. Keep the actual title, salary/total-compensation distinction, live-listing/application-form distinction, experience/location requirements and remaining model-specialization gap. No percentage alignment or hiring guarantee is claimed.

Keep C1–C6, H0–H15, M0–M7, existing runtime/evaluator, Anthropic scaling question and D022 priority. [NV1–NV3](../capstone/07-reference-implementation-spec.md#nvidia-coding-tools-specialization) refine one GPU candidate-to-verifier/performance path, one versioned developer-knowledge/profiler profile and one reviewed data-promotion contract. Reuse prior course contracts; no wholesale vendor-stack adoption or additional core benchmark. Status: **reviewed proposed design; unimplemented/unmeasured**. GPU supervision, trusted measurement outside candidate-controlled host code, permissions and retirement must be concretely frozen before execution. Old effort estimates exclude this extension. Revisit scope based on actual profiler/evaluation evidence; preserve negative outcomes and separate AI delivery from Huy's mastery.

**VI:** Scope mới phải tạo evidence tuyển dụng có ý nghĩa bằng cơ chế thật. Thêm NV1–NV3 là nối những phần đã có; không đổi toàn bộ project theo từng job post. Các requirement về nhiều năm kinh nghiệm, người dùng thật và ảnh hưởng tổ chức vẫn cần evidence ngoài một bản spec.

## D026 Continuous implementation by acceptance gates

**2026-10-10, Huy's instruction.** Remove the daily build-time constraint and supersede D022's provisional four-hour/80-hour estimate. Audit core plans/context, specify each component and execute continuously toward the product outcome. Keep human mastery separate and retain deadline-based scope decisions. Spending/account limits were not supplied by this instruction; local preparation/testing proceeds without paid inference or hosting. [Execution specification](../hackathon/04-execution-specification.md).

## D027 Supported repository repair source and bounded restart

**2026-10-10, AI engineering decision and measured delivery.** Reuse RuntimeStore/Harness/artifact/budget/execution primitives for one stateless Python function recipe and one patch worker. Full private inputs are hash-bound in `repair_spec` but kept in a separate supervisor-only store. Host final checks use fresh containers and sanitized results. Clean checkpoint resume retains native history, global task dispatch frontier, settled/unknown money and cumulative turns/tests; known final receipts are reused. Astra review repaired cross-attempt rewind, diff framing, outcome/failure display and complete event export. [Runbook](../hackathon/05-local-repair-runbook.md) and [independent review](../research/hackathon-2026-10-10/repair-independent-review.md). The [source-bound delivery verification](../research/hackathon-2026-10-10/repair-delivery-verification.json) records the real-Docker/restart delivery and phased checks.

Active-container process-loss reconciliation remains unsupported without a durable physical-instance journal. Fixture source/defaults and wider production/course/NVIDIA contracts remain preserved. This establishes local mock-controller/real-Docker mechanics, not live NVIDIA coding capability, production operation or Huy's mastery.

**VI:** Làm liên tục không bỏ qua gate evidence. D027 nối được một đường chạy thật nhưng giữ đúng phạm vi: clean restart đã đo, container đang chạy mà process mất thì vẫn phải giữ Unknown và reconcile, không retry mù.

## D028 NVIDIA numerical foundation before execution and performance

**2026-10-10, Huy-authorized implementation.** Follow [NV-S0–NV-S4](../capstone/07-reference-implementation-spec.md#ordered-implementation-slices). Freeze the RMSNorm purpose, owners, input envelope, independent oracle, numerical tolerance, byte identity and failure controls before Sol implementation. Astra owns design/review; separate Sol workers own reference source and distinguishing tests. NV-S0 is a trusted local CPU mathematics slice, not generated-code execution or a production verification receipt. It can proceed independently of course skills/LSP/compaction. Next shared dependency is the existing failure-evidence/regression contract; GPU build/measurement additionally requires concrete supervision and trusted timing boundaries. Preserve the hackathon runtime, original workloads and H0 mastery status. Only the tested slice is promoted to implemented; no claim of 100% role readiness or full NVIDIA completion.

**VI:** Đúng thứ tự nghĩa là tạo oracle trước khi tối ưu, và tạo boundary đo trước khi tin tốc độ. Agent viết code và agent viết test làm việc theo cùng contract nhưng khác implementation; reviewer kiểm những chỗ cả hai có thể cùng hiểu sai.

**Delivery evidence:** NV-S0 passed its bounded CPU review and tests; [verification](../research/nvidia-s0-verification-2026-10-10.json) and [two repaired review findings](../research/nvidia-s0-review-2026-10-10.md). Broader GPU/agent/data stages remain pending. This supersedes D025's blanket unimplemented status only for the numerical foundation; the historical role-audit evidence remains unchanged.

## D029 Bounded HTTP evidence and explicit paid-execution hold

**2026-10-10, spec-first implementation plus Huy’s direct instruction.** Freeze [the HTTP error contract](../hackathon/06-http-error-evidence-contract.md) before source changes. Native non-success diagnostics use a separate typed artifact, request binding, bounded decoded prefix/headers and supported credential redaction; retain Unknown effect and charge liability. Both ordinary duplicate replay and later succeeded-effect diagnostic replay refuse tool authority. Astra review and independent Sol tests repaired EOF/close classification and malformed-header normalization. [Verification](../research/hackathon-2026-10-10/http-error-verification.json) records current source, full/default and real-Docker selected checks and refreshed unpublished source/wheel. Historical E0/repair/NV-S0 evidence remains separately dated; counts overlap.

Huy’s answer is **“Keep paid execution disabled for now.”** Do not infer permission from available credits, a deadline or continuous-build preference. Local specifications/code/testing proceed; genuine provider calls and paid hosting require a changed instruction plus actual account/rate/bound/spending inputs. No human mastery, live-model capability, public deployment or competition outcome follows from this delivery. Active-case physical-instance journaling and arbitrary repository support remain separate gaps.

**VI:** Error body là dữ liệu để điều tra, không phải completion hay quyền tool. Kết quả source đã đo vẫn tách khỏi quyền chi tiền: xây liên tục không tự mở live inference, và deadline không thay được chỉ dẫn mới của Huy.


## D030 Repair shared evidence boundaries before extending NVIDIA execution

**2026-10-10, Huy-authorized codebase audit and spec-first repair.** Three Astra reviews reproduced ten defect groups; [the bounded specification](../research/codebase-refactor-spec-2026-10-10.md) preceded disjoint Sol implementation and [independent review](../research/codebase-review-independent-2026-10-10.md). Keep one RuntimeStore and evaluator. Tighten fixture/receipt attribution, complete physical observations, endpoint/model/protocol validation, factual chronology and static input admission. Independent review corrected an initial pricing assumption: token counters without the exact response model do not establish the applicable frozen rates, so both live adapters retain unresolved charge in that case. Historical settled records are not rewritten. [Verification](../research/codebase-review-verification-2026-10-10.json) binds the current source and checks.

The next new shared component remains development FailureEvidence/RegressionCase capture, followed by the existing context/skills/LSP and NVIDIA dependencies. No broad storage split, new engine, schema change, benchmark migration, training system or deployment is justified by these fixes. Preserve hackathon priority, paid-execution hold, historical evidence and H0 human learning status.

**VI:** Refactor phải sửa được một cơ chế sai có counterexample. Cùng số token không đồng nghĩa cùng giá; exit0 không đồng nghĩa một lệnh bị timeout đã hoàn tất. Các invariant này phải đúng trước khi dùng lại chúng cho GPU.

## D031 Capture failure evidence before proposing development regressions

**2026-10-10, Huy-authorized spec-first delivery.** Three Astra design/review lanes established the [frozen contract](../research/failure-regression-spec-2026-10-10.md) before Sol implementation and independent tests. Use one existing database read transaction for the bounded full task snapshot and committed events; append the capture helper without changing runtime mutators/schema. Preserve causal generation, exact candidate/grader/environment, artifact scope and whole-task costs. Two fixed data predicates create immutable pending development proposals; reviews are separate declared records. The adapter never grants execution, task acceptance, held-out status or human mastery.

Independent review required repairs to bounds, typed data boundaries, causal joins, immutable record validation and lineage. Two addenda were frozen before their repairs: unavailable accounting becomes null rather than misleading0; legitimate aggregate overspend remains exact beyond individual-row bounds. [Independent review](../research/failure-regression-independent-review-2026-10-10.md), [verification](../research/failure-regression-verification-2026-10-10.json) and [two-case demo — local-only](../docs/github-snapshot.md#omitted-local-evidence) retain actual source/test identities. Existing analyzer, workload population, human mastery and paid-execution hold remain unchanged.

Next course-derived source work is deterministic accepted context projection under its existing dispatch/activation/recovery contract. NV-S1 GPU boundary design may proceed independently. Hackathon conformance/live repair/submission retains priority when inputs and authorization permit; this local adapter does not advance those external gates. No broad mining, new evaluator, model training or automatic publication was added.

**VI:** Failure phải gắn đúng object trước khi trở thành bài học hay regression. Hash giúp giữ identity; không tự xác thực nguồn. Unknown không biến thành success khi bill về, và null không được đổi thành0 để báo cáo đẹp hơn.

## D032 — deterministic offloading with per-dispatch acceptance

**2026-10-10, Huy-authorized implementation.** Freeze [the contract](../research/context-offloading-spec-2026-10-10.md) before source changes; separate Astra design/review, Sol projection/runtime lanes and independent tests. Preserve schema 2 and legacy full-history behavior by accepting a versioned projection atomically with its model intent, rather than introducing a global context pointer that old writers could bypass. Deterministic offloading is explicit, capability-gated and backed by scoped reload; Anthropic remains full-history only. Raw history and all effect/billing knowledge remain authoritative.

Review repaired invalid typed checkpoint counters, stale projection retrieval and canonical JSON bool/int aliasing. The first full-suite run then exposed legacy provider-keyword and minimal-checkpoint compatibility failures; both were repaired and verified by the full suite and expanded independent review. Original failures remain preserved. Integration exposed missing scope on newly written checkpoints; frozen Addendum A adds scope to new records without rewriting historical evidence. Addendum B distinguishes canonical request identity from raw wire bytes. [Review](../research/context-offloading-independent-review-2026-10-10.md) and [verification](../research/context-offloading-verification-2026-10-10.json) bind **1171 tests and 156 subtests passed; 2 Temporal opt-in skips; local PostgreSQL/Docker enabled; Ruff passed**. Focused counts overlap with the full suite. Paid execution, release publication, semantic recall/performance and human mastery remain unclaimed.

Next bounded course design is immutable skill activation using stable prompt/context identities; semantic summaries need their own accounted requests and post-activation evaluation. Required hackathon release/access work keeps priority. No new curriculum, evaluator, provider dependency or GPU requirement was introduced.

## D033 Frozen offline candidate before the next runtime extension

**2026-10-10, Huy-authorized spec-first delivery with separate implementation, installed tests and independent review.** [The release contract](../research/offline-release-spec-2026-10-10.md) fixes curated source identities before artifact construction. Preserve original runtime/schema/lock/workload/historical bytes; reject missing, added, changed or aliased inputs. The local cache could not support a hash-checked base install. Frozen Addendum A permits only original public locked binary wheels as separate online preparation; offline build/install/acceptance retain strict hashes and no index. No paid model/account/hosting/pull/publication action follows.

[Verification](../research/offline-release-verification-2026-10-10.json) and [independent review](../research/offline-release-independent-review-2026-10-10.md) bind 52 packaging checks, two external fresh-venv runs, exact installed origins/assets, native mocked repair and clean restart, independent patch application, accepted context retrieval/recovery and Unknown no-resend/once-only billing. Extracted source rebuild reproduces the archive and wheel member bytes; the wheel container hash itself differs on rebuild. These are same-machine independent AI checks, not public judge access, fresh-machine qualification, production operation or human mastery.

Prepare [immutable skills](../research/immutable-skills-spec-2026-10-10.md) in parallel as reviewed frozen design only. Reuse successful ordinary load receipts, distinguish loading from later request disclosure, preserve schema 2 and verify direct original provenance with a 64-record bound. Next bounded runtime implementation follows S1–S7; no installation/script execution/hot reload or authority escalation is added by design. Preserve H0 learning status and G1/live-G2/public-G5 hackathon priorities.

## D034 Immutable capture before runtime skill activation

**2026-10-11, Huy-authorized smallest slice.** Freeze [the capture contract](../research/immutable-skills-capture-spec-2026-10-11.md) before code, specializing dependency step2 of [the full immutable-skills design](../research/immutable-skills-spec-2026-10-10.md). Astra reviews architecture and implementation; separate Sol agents own code and distinguishing tests. One authored fixture is sufficient to test source → immutable scoped artifacts → validated catalog → exact resource bytes. Retain strict closed identities, bounded parser events, no-follow descriptor traversal and independent corruption/mutation tests. PyYAML6.0.3 adds one exact cached dependency; shared artifact reads gain an optional lower per-call cap.

[Independent review](../research/immutable-skills-independent-review-2026-10-11.md) accepted the bounded slice after deep-JSON, pre-allocation and exception-context repairs. [Verification](../research/immutable-skills-verification-2026-10-11.json) owns current evidence. These helpers grant no tool authority. Next: broker tools and receipt-derived loaded-state validation, then actual accepted-request disclosure and fresh-owner recovery. Partial S1/S6 data evidence does not complete S7/A/R runtime gates. Preserve schema2, original42 workloads/82 locked assets, old release artifacts, hackathon priority and the paid-execution hold. New source and its scratch package do not inherit October10 installed acceptance. Human H0–H15 mastery remains unassessed.

**VI:** Đầu tiên chứng minh bytes và identity ổn định. Bước sau mới chứng minh ai được load, request nào đã thấy skill và owner mới có quyền gì. Snapshot đúng chưa đủ để agent được phép hành động.

## D035 Broker receipt evidence before accepted catalog disclosure

**2026-10-11, Huy-authorized dependency step3.** Independently review and freeze [the broker contract](../research/skills-broker-spec-2026-10-11.md) before separate Sol implementation/testing. The existing context-v1 acceptance cannot prove which catalog or loaded state was advertised. Therefore deliver an explicitly configured scripted broker seam, with ephemeral `broker_skill_loads_v1`; do not silently promote its records to future accepted SkillsState. A successful ordinary receipt and exact immutable result/source association establish loaded membership. Unresolved duplicates never rerun; known duplicates validate and reuse their original source/result, even after a newer pin. A new call returns a direct primary-load reference. Two calls cannot race past the authoritative frontier into competing primary loads.

Reuse schema2 and ordinary zero-bound dispatch/receipt semantics; cap current-attempt dispatch/direct-receipt evidence at64 records before materialization and reserve room for new intent+receipt. No artifact I/O inside authority transactions. Valid-package resource calls remain `not_disclosed`; catalog mismatch refuses before intent. Only explicit frozen capabilities admit the broker. Preserve historical specs/releases, benchmark locks, hackathon priorities and H0 mastery. The [independent review](../research/skills-broker-independent-review-2026-10-11.md) and [verification](../research/skills-broker-verification-2026-10-11.json) own delivery evidence. Next: versioned accepted catalog/provider-context requests, then typed checkpoint/fresh-owner recovery. Paid execution remains disabled; user-supplied credit availability does not change execution authorization.

**VI:** Receipt trả lời “load đã commit chưa”; accepted request trả lời “model đã được cung cấp đúng catalog/body nào”. Hai bằng chứng khác nhau, nên ta giữ hai bước riêng. Promo/credit không thay budget authorization hay quyền gọi model.

## D036 Accepted request disclosure before resource authority and recovery

**2026-10-11, Huy-authorized dependency step4.** Freeze [the integration contract](../research/skills-disclosure-spec-2026-10-11.md) before implementation; Astra owns architecture/independent review, separate Sol agents own bounded runtime and tests, and the coordinator owns exact native mock demonstration and document integration. The store remains schema2. Explicit context-v2 acceptance binds immutable catalog/config, receipt-derived SkillsState, fixed prompt renderer, tools, projected history and exact request identity. Validate the complete durable source history, not just the load receipt; internally fingerprint bounded dispatch/receipt rows before the authority transaction and recheck without artifact I/O under the lock.

A load changes membership after its successful receipt; resource authority comes from the emitting request's previously accepted state and current frozen capability. Same-response load+read denies. Known retries retain their historical empty/loaded state and original bytes without new publication, send, event or cost. Current derivation is required only for new acceptance. Default paths and broker-v1 remain separate, with no automatic promotion, profile switch or capability escalation. Preserve opaque provider protocol fields and canonical request identity separately from raw HTTP wire serialization.

The [independent review](../research/skills-disclosure-independent-review-2026-10-11.md) and [verification](../research/skills-disclosure-verification-2026-10-11.json) own evidence and limits. Step5 typed checkpoint/fresh-owner recovery is deliberately deferred: reject restore/pause and return explicit unsupported-checkpoint status without checkpoint artifacts/events. Do not write a legacy-looking checkpoint that loses SkillsState. Preserve original 42 workloads/82 assets, prior specs/releases, hackathon essentials, paid-execution hold and H0–H15 human evidence. No live inference, new release acceptance or job-readiness claim follows.

**VI:** Load receipt trả lời “đã lấy body nào”; accepted request trả lời “model đã được gửi state/body nào”; owner/capability trả lời “call hiện tại có quyền gì”. Recovery phải mang đủ cả ba chuỗi chứng cứ nên là bước kế tiếp riêng, không suy ra từ việc replay cùng attempt thành công.

## D037 — bounded readiness with separate data, execution and physical authority

**2026-10-11, Huy-authorized multiagent audit/specification/implementation.** [The dependency plan](../research/system-readiness-plan-2026-10-11.md) freezes skills step5 first, builds independent offline-serving and trusted-GPU preparation lanes, then integrates a separately frozen physical-instance journal before installed acceptance. Preserve one RuntimeStore/evaluator and store schema2; typed record profiles change only their bounded consumers. Public frontier sources inform falsifiable decisions, not claims about private implementations or our live performance.

Typed checkpoints keep the accepted pre-request state separate from post-turn membership, original load provenance and fresh-owner authority. Missing historical evidence never authorizes replay to recreate it. Atomic persisted pending caps bound local fixture admission; service-root incarnation and actual child lifetime protect honest restart/readiness without claiming backup rollback detection. Docker intent/nonce precede create; immutable ID plus original daemon/policy and current cleanup authority govern removal. Zero-match unbound creation remains unresolved. Physical retirement cannot settle money, establish a verifier pass or resend a tool.

Independent review repaired skills replay reconstruction/unbounded reads, missing/replaced service-root database acceptance, GPU Boolean/numeric identity and contradictory completion, and stale-controller cleanup after preflight. Fault records remain preserved. The trusted authored probe defaults to no execution; full generated-kernel isolation and device retirement are still separate unimplemented contracts. The [current candidate](../releases/README.md) has independent outside-checkout installed acceptance; October10 artifacts remain immutable.

Follow real dependencies: source/installed qualification → separately authorized dedicated-GPU or live-provider experiments → deployment containment/restore/load/canary/SLO evidence. Dynamic replanning, semantic compaction, LSP, generalized repositories and full live-service operations remain explicit source gaps rather than claims hidden behind “hardware pending.” Required hackathon conformance/live repair/access retains priority. Paid execution, publication and H0–H15 human mastery remain unchanged; no hiring or production-readiness guarantee follows.

**VI:** Ba authority không thay nhau: checkpoint là dữ liệu, claim là quyền, retirement là bằng chứng tài nguyên đã thu hồi. Các sửa lỗi này làm reference đáng tin hơn trong phạm vi đã test; chúng không tạo ra kết quả model/GPU chưa chạy.

## D038 Research informed mentoring and decision based allocation

**2026-10-11, Huy's explicit mentoring-skill update request.** Strengthen the reusable [first-principles mentor — local-only](../docs/github-snapshot.md#omitted-local-evidence) around purpose/value, exact code/data/tensor traces, English plus complementary Vietnamese, and the smallest experiment that changes a decision. Public 2026 OpenAI/Anthropic/NVIDIA reports inform practice; no private routine, top-percentile status or guaranteed career outcome is claimed. [Audit and worked examples](../research/mentoring-operating-model-2026-10-11.md).

Keep AI reference delivery and Huy's independent prediction/diagnosis/transfer as separate evidence. Preserve H0–H15, one runtime/evaluator and the implementation-first authorization. Correct stale learn-before-build wording, historical-current navigation and outdated extension status without rewriting frozen results. Old hour estimates are historical; required conformance, useful repair and judging access take priority over optional pilots. Paid execution remains disabled. A learning request does not authorize unrelated production rollout.

**VI:** Tinh thần “How hard can it be?” là dám bắt đầu từ một cơ chế nhỏ và chịu sửa giả thuyết khi evidence khác dự đoán. Khi bí, đổi cách biểu diễn và tìm mắt xích đầu tiên chưa rõ; AI viết code không thay cho bằng chứng em tự hiểu và transfer được.

## D039 Offline qualification binds evidence before live conformance

**2026-10-11, explicit end-to-end implementation request.** Deliver the bounded [qualification contract](../research/provider-qualification-spec-2026-10-11.md) in dependency order, with separate implementation/tests, independent review and fresh installed acceptance. Preserve one runtime/harness/evaluator, existing repair authority, schema2, lock and workloads. A supplied ProviderApproval is an assertion; the two-request native mock transcript is an observation; handoff is point-in-time advisory only.

An independent canonical-reindex failure showed that immutable report files alone did not bind the original manifest. Pin its full digest in the durable probe contract and reconstruct exact request/receipt/history/accounting on inspection. Unknown keeps its liability and cannot resend. Original prepared repair is read through a WAL-aware snapshot and remains unchanged. The [verification](../research/provider-qualification-verification-2026-10-11.json) retains43 qualification tests,381 regression tests, six reviewer controls, three rejected mutations and installed rc4. Preserve rc1/rc2; rc3 was built but not accepted because nested CLI origin checks needed completion. rc4 includes all seven checks. Human mastery and paid/live/public/GPU holds remain unchanged.

**VI:** Không thêm runtime hay benchmark mới để lấp gap nhỏ. Ta nối đúng identity và kiểm tra failure mode quyết định; mock pass không nâng thành G1/G2 thật hoặc quyền thực thi.

## D040 Trace core constraints through real serving and production evidence

**2026-10-11, Huy's explicit follow-up mentoring request.** Extend the reusable first-principles skill and project instructions with a two-way trace: derive substantive components from explicit mathematical/physical constraints and failure assumptions, then follow their actual implementation and consumers to real workload and operational evidence. Distinguish policy from law, safety from progress, intent from effect/receipt, and local correctness from an operated service. Primary Lamport, Saltzer/Reed/Clark, AWS, Google SRE, Columbia, Berkeley Lab, Anthropic and versioned NVIDIA documentation ground the [reusable reference — local-only](../docs/github-snapshot.md#omitted-local-evidence).

The [H0 companion](../study/packets/H0-first-principles-to-production.md) maps the inspected repair CLI, fixture HTTP and offline qualification paths separately and derives one complete FIFO example. It adds no module, runtime, deployment or human mastery claim. Current rc4 evidence and paid/live/public/GPU restrictions remain intact. Production depth follows the selected workload; an API-backed agent does not acquire a GPU prerequisite merely to make the explanation deeper.

**VI:** Mỗi component phải trả lời được vì sao nó tồn tại, invariant nào nó giữ, lỗi nào làm giả định sai, và điều đó ảnh hưởng user ra sao. Đi tới production nghĩa là nối tới đúng evidence còn thiếu, không chỉ thêm một ô “production” vào diagram.

## D041 Demanding mastery through attributable evidence

**2026-10-11, Huy's explicit resilience and mastery request.** Treat Huang's verified SIEPR remarks as motivation for persistence and learning from setbacks. The [source note — local-only](../docs/github-snapshot.md#omitted-local-evidence) separates entrepreneurial advice from research on instruction after problem solving and delayed retrieval, including their limits. The chosen mentoring contract demands evidence of understanding, without making distress or elapsed effort the objective.

Strengthen the existing [human gate rubric](../docs/05-mastery-tracker.md#self-check-menu-optional): derive, predict, trace, debug, transfer and retrieve later. A bounded learner attempt receives causal feedback and graduated help; an exposed solution requires a fresh independent reassessment. Record assistance and pending retention in the single session template. Honor requests for an answer, pause or mode change and attribute their effects on assessment honestly. Reuse valid evidence and assess core concepts across sessions rather than quizzing every small action.

Correct the stale study README instruction that blocked building on a learning gate and select the current runtime packet. Preserve implementation-first authorization, all H0–H15 statuses, source/installed evidence, prior sessions and paid/live/public/GPU holds. No engineering rerun is implied by this mentoring-only edit.

**VI:** Ta nghiêm túc với bằng chứng em tự hiểu: sai thì tìm đúng nguyên nhân, học phần còn thiếu rồi tự thử bài khác. Agent có thể làm reference trước; sự bền bỉ thể hiện ở cách em sửa mô hình tư duy, không phải ở việc chịu mệt hoặc đồng ý với lời giải của AI.

**Superseded 2026-10-16 by [D046](#d046-production-backward-learning-replaces-mastery-gates):** the rubric is now an optional self-check menu, not a requirement.

## D042 Live execution enabled for the hackathon path

**2026-10-13, Huy's explicit instruction ("yes absolutely 100%").** Supersedes D029's paid-execution hold **for the hackathon path**: live Nebius Token Factory calls with an NVIDIA open model are permitted for G1 conformance, G2 useful repair and G5 judge access. Huy did not set a dollar cap. A frozen micro-USD ceiling and absolute deadlines remain **required inputs** of `repair-prepare`, so the system cannot run uncapped. They limit how much a fault such as a runaway loop can spend; they do not limit ambition. **Proposed default, raise on evidence by a later decision:** at most 5 USD per repair task and 300 USD in total through December 16 judging, including judge access. Credentials stay server-held in `NEBIUS_API_KEY` and are never stored in the repository. Account catalog, model identity and rates must come from Huy's actual account (`evidence.kind=operator-verified`). Publication of the public repository, video and test build is in scope for G5; each actual publish action is confirmed at the time it happens. Hostile-code containment remains unqualified: live runs stay on the supported, authorized Python recipe.

**VI:** Mở live call không có nghĩa là bỏ trần chi phí. Trần là input bắt buộc của hệ thống: nó giới hạn thiệt hại khi có bug, ví dụ một vòng lặp chạy cả đêm, chứ không giới hạn tham vọng. Quyền gọi model thật và quyền chạy code lạ là hai việc khác nhau; cái thứ hai vẫn chưa được chứng minh an toàn.

## D043 Production evidence is the primary track

**2026-10-13, Huy's stated direction.** Runway is not a constraint. The goal is a real project serving real production use and showing engineering judgment derived from first principles, not credentials. Consequences:
- The hackathon live repair is the first production instance.
- Expert-platform labor and eval consulting are **dropped** as income paths, not deferred.
- NVIDIA Vietnam remains an option, not a track.
- The product hypothesis beyond the hackathon is chosen **after G2 produces real failure and cost data**, by one preregistered discovery experiment with kill criteria. No product wedge is decided yet.

Acquirers and frontier labs buy users, revenue or a team that demonstrably shipped and can defend its system. So human understanding is an operational requirement, not a side track. The first live run's trace becomes the H0 lesson under the existing rubric. No mastery result is recorded by this decision. Any path toward users submitting arbitrary repositories must first close the hostile-code containment gap in [coverage](../capstone/08-implementation-coverage.md).

**VI:** Founder không cần nhiều năm kinh nghiệm, nhưng cần người dùng thật và cần tự hiểu hệ thống của mình. Sự cố production lúc 3 giờ sáng do người hiểu hệ thống xử lý, không phải do agent đã viết code. Vì vậy học H0 trên chính trace chạy thật là một phần của việc ship.

## D044 Build-ordered mastery route

**2026-10-14, Huy's explicit request to refactor the learning plan for mastery while building.** Order the existing H0–H15 modules by the live build stages S0–S6 (before G1, G1, G2, G5, product discovery, production, research), and learn each concept on the real artifact its stage produces. Tier modules by the gate that needs them and the capability they prove, without percentages: core H0–H4 and H8; gate H7, H11 and H15; supporting H5, H6 and H9; research H10 and H13; NVIDIA specialization H12 and H14. Each stage names one decision Huy owns and records with alternatives, evidence and reversibility. This supersedes the CPU-only first six sessions, which predate D042/D043. Anthropic and NVIDIA alignment uses the audited postings; OpenAI alignment uses public engineering reports only. H0–H15, C1–C6, the rubric, the tracker and the session template are unchanged, and no mastery is recorded. A trace check while writing the route found the live Nebius path is non-streaming: SSEDecoder and ToolStream remain the H2 streaming exercise, not the G1 trace. [Route](../docs/02-mastery-learning-plan.md#build-ordered-route-2026-10-14), [S0 prompts](../study/sessions/2026-10-14-H0-live-G1-prediction.md).

**VI:** Không thêm module hay ledger mới. Ta chỉ đổi thứ tự học theo thứ tự build, để mỗi khái niệm được học trên artifact thật lúc nó vừa xuất hiện, và để mỗi giai đoạn có một quyết định em tự chịu trách nhiệm. Bằng chứng mastery vẫn chỉ đến từ dự đoán, trace, debug, transfer và nhớ lại của em.

**Partly superseded 2026-10-16 by [D046](#d046-production-backward-learning-replaces-mastery-gates):** the stage order and each stage's artifact stand; the rubric, tracker and session-structure conditions do not.

## D045 Capped, verifier-shaped contract income reopens

**2026-10-14, Huy's delegated decision (follow-up mentoring, about 15:30 ICT).** D043 dropped expert-platform and eval-consulting income on the premise that runway isn't a constraint. That premise no longer holds. Runway is about 45 days (to about 2026-11-28), and the median technical hiring path (40 days from application to accepted offer, in Ashby's data) pays a first salary in mid-December or later. This reverses D043's income clause, narrowly:
- verifier-shaped contract work only: coding RL environments, graders and code evals, with no generic labeling;
- at most 10 h/week, never in the hackathon blocks;
- Huy does the sign-ups and screening this week; paid work starts after submission (Oct 30), in November's building block, or after G2 from ladders Block D if a strong project needs an earlier start;
- client material never enters this repository or any public artifact.

D043's other consequences stand: production evidence remains the primary track, and the product hypothesis is still chosen after G2 by one preregistered discovery experiment. Its proposed criteria are in [MENTOR_GUIDE §10.5 — local-only](../docs/github-snapshot.md#omitted-local-evidence). Reviewed at the Nov 1 retrospective.

**VI:** D043 bỏ thu nhập hợp đồng vì cho rằng runway không phải là ràng buộc. Với runway khoảng 45 ngày, và con đường tuyển dụng theo trung vị chỉ trả lương đầu tiên từ giữa tháng 12, tiền đề đó không còn đúng. Ta chỉ mở lại phần việc có hình dạng verifier (RL environment, grader, eval cho code), có trần 10 giờ mỗi tuần và không bao giờ lấn vào khối hackathon. Loại việc này vừa trả tiền kịp trong cửa sổ runway, vừa luyện đúng kỹ năng mà vai trò Code RL kiểm tra.

## D046 Production-backward learning replaces mastery gates

**2026-10-15, Huy's explicit instruction** ("remove all the mastery rules"); the concrete edit list was approved with "Yes" on 2026-10-16. Huy's reasoning: learning all fundamentals first and building afterwards loses what was learned and forces relearning. Frontier engineers start from systems that run in production, read the code as the source of truth, and trace backward to first principles, which is also where new engineering or research becomes possible.

**What changes:**
- **The unit of learning is a production trace.** It starts from a real artifact: a live run, an incident, a measured cost, a verifier verdict, or a production codebase read as source. It names the surprise, then traces down through our code, libraries, protocol, serving, model, kernels, hardware and math. It stops at the layer where Huy can predict the behavior and change it deliberately, and ends in an output: a fix, a regression test, a write-up, an upstream issue or pull request, or an experiment.
- **The tracker becomes a [trace log](../docs/05-mastery-tracker.md)** with no statuses. The session template becomes a [trace note](../study/templates/session-note.md). H0–H15 stay as a concept index that traces draw on, not a sequence to complete.
- **Rubric and gates go.** The six checks of D041 remain only as an optional [self-check menu](../docs/05-mastery-tracker.md#self-check-menu-optional). Mastery gates, "not demonstrated" statuses, required retrieval intervals, hint-fading rules and session quotas are removed.

**Superseded:** D041's rubric as a requirement; D044's rubric, tracker and session-structure conditions (its stage order and the artifact each stage produces remain); and D012's "build the reference, then master its mechanisms" order for learning. D012's authorization for AI-built implementation is not affected.

**Unchanged, because these are not mastery rules:**
- Huy's fields hold only Huy's words and actions, and AI help is labeled ("Never invent human evidence").
- Proposed, reported, measured and demonstrated results stay separate.
- Safety and ownership rules stay: no secrets in the repository, chat or logs; no push and no remote; paid calls only within the frozen ceiling and with a fresh yes; every publish needs a yes; commits only when asked; no personal-finance amounts.
- The G1 → G2 → G5 critical path and the deadlines in D044 and the brief.
- S0 stays as a **pre-registration** before the first paid call: experiment design, not a test. Its prompts and its secrecy are unchanged, and Huy can drop it by saying so.

**Also recorded here:** the public submission snapshot is licensed **Apache-2.0** (Huy, 2026-10-15; [G5 drafts](../hackathon/07-g5-submission-drafts.md)).

**Status:** active. Review at the Nov 1 retrospective by counting traces that ended in a prediction that came true or in a fix. If no traces were recorded, the problem is execution, not method. Do not write a new learning plan in response.

**VI:** Bỏ "cổng" mastery, không bỏ sự trung thực. Học bắt đầu từ thứ đang chạy thật (một call live, một sự cố, một con số chi phí, hoặc code production của người khác đọc như nguồn sự thật), rồi đào xuống từng tầng cho đến khi em tự dự đoán và tự sửa được. Mỗi trace phải kết thúc bằng một thứ dùng được: bản sửa, test, bài viết, issue hoặc PR upstream, hoặc một thí nghiệm mới. Các rule an toàn không đổi vì chúng bảo vệ tiền, key và quyền publish, không phải để chấm điểm việc học.


## D047 Private GitHub collaboration snapshot

**2026-10-16, Huy's explicit instruction:** create a repository and push the current codebase; Huy selected **private — invited collaborators only**. Use `andreidhoang/coding-agent-mastery` with a separate current-file snapshot and fresh Git history. Preserve the original workspace's local rollback history without adding a remote. Include current source, tests, locks, authored workloads, core docs, context, learning packets and research summaries, including uncommitted documentation changes. Exclude credentials, raw runs, databases, generated release trees, environments, downloaded reference payloads and private external material. Convert navigation for GitHub and preserve provenance for excluded artifacts.

This private sharing action does not satisfy public HR07/judge access, authorize invitations, or change live/GPU/deployment authority. Root Apache-2.0 terms use the already selected project license; cited upstream projects/dependencies retain their own licenses. Historical acceptance remains source-bound; validate the exported checkout separately.
