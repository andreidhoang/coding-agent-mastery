# Implementation architecture audit — 8 October 2026

**Author/evidence:** AI architecture review, prepared before implementation acceptance. Huy requested source delivery before subsequent first-principles study. This audit uses the current capstone SYS/RT/EV/OP contracts and reopens primary sources; it does not award human mastery, production readiness or a frontier-lab hiring outcome. No vendor result below is reproduced by this audit. The concrete implementation contract is [capstone 07](../capstone/07-reference-implementation-spec.md).

**VI:** Ta dùng public research để chọn giả thuyết và boundary, không dùng tên công ty để chứng minh code của mình đúng. Bằng chứng local phải có run/test riêng.

## Primary evidence rechecked

Pages were opened on **2026-10-08**. Documentation is a live interface, not a pinned historical implementation. Publication dates below come from the primary page where available. Only narrow claims relevant to the implementation are retained.

| Source | Documented/reported evidence | Our inference and decisive check |
|---|---|---|
| [Anthropic Managed Agents](https://www.anthropic.com/engineering/managed-agents), 2026-04-08 | Separates session log, harness and sandbox, allowing independent replacement; describes keeping credentials out of generated-code environments | Separate authority/event store, model loop and supervisor. Kill each independently; reconstructed execution must retain constraints and liabilities |
| [Cursor cloud-agent lessons](https://cursor.com/blog/cloud-agent-lessons), 2026-06-02 | Reports environment reconstruction and durable execution as practical cloud-agent challenges | Provide real workflow/environment adapters and exact environment identities; do not infer vendor-private topology or our fleet capacity |
| [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), 2025-06-13 | Reports orchestrator/worker research benefits alongside substantial token use; notes dependency-heavy coding is harder to parallelize | Keep bare single-agent and candidate N=1 distinct; compare N=1/2/4 under shared ceilings and inspect integration overhead |
| [Temporal Activities](https://docs.temporal.io/activities), live | Activities can perform nondeterministic work and may retry; documentation recommends idempotent behavior | Workflow durability does not make external side effects exactly once. Store intent/dispatch/receipt and retain unknown effects |
| [SQLite transactions](https://www.sqlite.org/lang_transaction.html), live | Multiple readers but one concurrent writer; `BEGIN IMMEDIATE` begins a write transaction and may encounter contention | Use it for local semantics; do not claim PostgreSQL concurrency behavior from SQLite tests |
| [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html), version 18 documentation | Row-locking clauses exist; `SKIP LOCKED` trades consistency for queue-like concurrency | Use one authority-row lock for reference mutation ordering; later optimize only with measured contention and invariant tests |
| [Docker Engine security](https://docs.docker.com/engine/security/), live | Describes kernel isolation, resource controls and daemon attack surface as separate concerns | No Docker socket, host home or service secrets in candidate containers; container startup alone is not isolation proof |
| [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), live | Documents replayable response output, encrypted continuation content and current reasoning-context behavior | Preserve opaque provider items and supported linkage verbatim; summaries are not a provider protocol adapter |
| [Anthropic statistical evaluation guidance](https://www.anthropic.com/research/statistical-approach-to-model-evals), 2024 | Recommends paired differences to exploit shared question structure | Aggregate trial results by task and bootstrap paired task/repository blocks; missing assigned outcomes remain visible |
| [vLLM automatic prefix caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/), live | Documents reuse of prefix KV computation and workload-dependent applicability | A cache-policy simulator can test reuse accounting but cannot establish observed GPU speedup |
| [PPD preprint v2](https://arxiv.org/abs/2603.13358v2), 2026 | Studies prefill distinctions in multi-turn serving | Preserve first-turn/warm-append/idle/eviction classes in a future serving experiment; do not assume one cache policy wins |
| [vLLM–Mooncake report](https://vllm.ai/blog/2026-05-06-mooncake-store), 2026-05-06 | Reports a particular cache-sharing serving configuration/workload | Treat as experiment motivation; capstone needs its own hardware, workload, latency and quality measurements |

**VI:** “Reported” là kết quả tác giả công bố trong điều kiện của họ. Chuyển sang hệ thống này chỉ tạo hypothesis. Ví dụ cache reuse có thể giảm prefill nhưng queue hoặc integration vẫn làm task chậm hơn.

## Why these boundaries are necessary

There is no atomic transaction spanning a database, model provider, filesystem, workflow service and human review. Suppose the controller commits intent, changes bytes and crashes before recording a result. The bytes may be correct while the database cannot prove whether the effect happened. Automatically retrying confuses absence of evidence with evidence of absence. Therefore the runtime requires three separate objects: logical action identity, physical dispatch identity and reconciled receipt. This is a consequence of the failure boundary, independent of framework choice.

**VI:** Receipt bị mất không làm effect biến mất. Từ đây suy ra cần `unknown`, chứ không phải thêm `try/except` rồi gọi lại mọi thứ.

Similarly, a lease is an authorization time window, not a process-kill signal. A worker can remain alive after its lease expires. Physical slot accounting must retain that environment until trusted retirement is observed, while the authority store rejects its late accepted writes. The resource invariant and the ownership invariant address different failure modes; either alone is insufficient.

**VI:** Fence chặn worker cũ trở thành “sự thật”; cleanup chặn nó tiếp tục tiêu tài nguyên. Cần cả hai vì database không tự tắt được process ở máy khác.

The coarse PostgreSQL authority lock is an intentional implementation choice: every mutator obtains the same lock before checking state and writing events/receipts. For a bounded small reference this minimizes subtle inconsistent lock orders and shared-budget races. It is not a claim of scalable control-plane throughput. SQLite and PostgreSQL share domain commands and schema through SQLAlchemy; each backend still needs its own connection/concurrency tests. External work remains outside the lock to prevent long model/tool calls from blocking all admission.

**VI:** Tối ưu trước bằng cách tách lock có thể tăng throughput nhưng mở lại race. Ta giữ reference dễ chứng minh, đo contention, rồi dùng experiment để quyết định có cần fine-grained locking không.

## Critical design-review findings

| Failure risk | Required resolution in source/tests |
|---|---|
| Worker can forge verifier identity through an ordinary store/API field | Verifier and publication routes are trusted control-plane capabilities; worker tools cannot call them |
| Same hash accessible across tenants | Artifact ID membership is tenant/task-scoped; hash never grants read authority |
| A retry uses a new transport ID to evade business idempotence | Canonical action/claim/submission identities bind parameters and retained terminal receipts |
| Partial JSON accepted because a stream ended | Explicit complete-item state, bounded parsing and supported terminal semantics; disconnect cannot execute incomplete calls |
| A late receipt reactivates cancelled work | Settlement writes only effect/billing knowledge, never execution ownership or accepted result pointers |
| Claim reserves 40 and dispatch additionally reserves 12 | Transfer allowance to dispatch exposure, keeping total liability counted once per scope |
| Provider returns actual charge above reserved upper bound | Surface violation, contain further admission and retain real charge; never truncate accounting to fake invariant success |
| Expired sandbox lease releases physical slot | Release only after trusted teardown/no-environment observation; partitions retain slot |
| Old verification reused after semantic merge | Verify exact reconstructed integrated tree and all grader/environment identities |
| Restore reuses historical epochs from an old backup | Fresh service incarnation, quarantine, fence all old actors and reconcile beyond-snapshot effects |
| Event cursor sequence reused across restoration | Bind incarnation/tenant/task, require explicit reset and report lost history frontier |
| DB outage followed by local execution fallback | Fail closed; no effect without durable intent and admitted reservation |
| Docker unavailable followed by host subprocess fallback | Fail closed for production profile; trusted fixture mode must be chosen explicitly |
| Synthetic N=4 fixture mislabeled coding scaling | Separate simulation, fixture, live-model and held-out outcomes in manifest/report |
| GPU absent but estimated numbers presented as benchmarks | Produce explicit skipped result; estimates carry units, assumptions and simulated label |

**VI:** Bảng review tập trung vào false success: hệ thống trông như chạy được nhưng có thể nhận nhầm output, bỏ nợ hoặc gọi simulation là research result. Test phải làm lỗi cụ thể này lộ ra.

## Quantitative checks and exact trace

Let task budget be `B=100` integer units. The state starts `(spent,reserved)=(0,0)`. An admitted attempt allowance of 40 yields `(0,40)`. Transfer 12 to dispatch D without changing total reservation. If D times out, reservation remains 40 until unused allowance is explicitly released or reconciled. Releasing the other 28 leaves `(0,12)`. A late supported receipt charging 9 settles D to `(9,0)`, releasing 3. Duplicate receipt changes nothing. A new request needing 92 now fails because `9+92>100`. Task, tenant and service scope sums enforce the same liability against separate limits; adding those totals would triple-count cost.

**VI:** Đây là trace giả định để phân biệt reservation transfer với double counting. Một unit test cần quan sát từng state và duplicate receipt, không chỉ tổng cuối cùng.

For standard dense KV tensors, let layers `L`, batch `B`, cached positions `S`, KV heads `Hkv`, head width `D` and element width `w` bytes. Each layer stores two tensors, K and V, with `B*S*Hkv*D` elements each; therefore `M_KV=2*L*B*S*Hkv*D*w` bytes. For a tiny example `L=2,B=1,S=3,Hkv=1,D=2,w=4`, storage is 96 bytes, excluding metadata. Query-head count does not multiply KV storage in grouped-query attention. A CPU implementation can validate tensor indexing, masking and full-vs-cached equivalence; it cannot validate GPU memory allocator residency or bandwidth.

**VI:** Hãy theo một phần tử `K[layer=1,batch=0,position=2,head=0,dim=1]`: nó được tạo khi token thứ ba đi qua projection, giữ lại để query tương lai đọc. Công thức byte đếm số phần tử thật được lưu, không đếm số query head cùng đọc nó.

For team size N, use `T_N=T_serial+T_parallel/N+I_N` only as a planning baseline with fixed work and balanced branches. Actual agents can change work, quality and resource consumption. Freeze common aggregate ceilings, then measure achieved concurrency, discarded work, conflicts, queueing and independently verified outcomes. Record hosted API tokens/dollars as billing/resource proxies; provider-internal FLOPs and prefill/decode timings are unavailable unless specifically exposed.

**VI:** Thêm worker có thể tăng lượng việc thay vì chia cùng lượng việc. Vì vậy chỉ vẽ speedup theo N mà không giữ task, budget và grader sẽ không trả lời câu hỏi scaling.

## Delivery acceptance and deferred validation

The requested delivery includes source bodies for local and production-target paths, executable fault controls, evaluation/analysis and CPU reference research. External services/hardware are not reasons to substitute a different product, but unavailable dependencies must be labeled at the exact adapter boundary. Test installed infrastructure when available; preserve evidence separately from source completeness. The requirement matrix in [capstone 07](../capstone/07-reference-implementation-spec.md#requirement-coverage-and-evidence-gates) specifies expected source versus operational proof.

At audit creation, no new implementation tests were run by this architecture role. Final delivery must replace any assumed status with observed file/test evidence. It must report at least: local fixture completion; SQLite race/fault tests; actual PostgreSQL tests if run; container probes if run; Temporal import/integration/history-replay scope; provider parser versus live-call scope; CPU numerical results; GPU run/skipped status; evaluation fixture versus held-out scope; remaining human/operational gates. Never mark SYS/RT/EV/OP wholesale complete from a green unit suite.

**VI:** Source hoàn chỉnh và evidence chưa đủ có thể cùng đúng. Cách báo cáo tốt nói rõ code nào đã chạy ở môi trường nào, lỗi nào đã gây ra và claim nào vẫn chưa được chứng minh.

## Remaining decisions for the implementation reviewer

- Keep the full public method contract synchronized with actual code; review transaction atomicity and trust boundaries after integration.
- Verify resource limits are enforced, not merely fields in a manifest. Explicitly identify any unsupported disk, cgroup or process-tree limit.
- Ensure restore never accepts an operator's unsupported assertion that old effects are settled; require inspectable observations or remain quarantined.
- Freeze realistic task registry/model/rates/spend/sample/stopping rules before paid or held-out experiments. Calibration tasks cannot masquerade as the diagnostic 36-task set.
- Preserve Huy's current mastery status. Build delivery provides code-reading targets for subsequent first-principles study, not invented prediction/teach-back evidence.

**VI:** Sau build, bài học bắt đầu từ đúng transaction, tensor và failure trace đã lưu. Reviewer độc lập và Huy vẫn phải tự tái tạo kết luận; AI không được điền thay bằng chứng đó.
