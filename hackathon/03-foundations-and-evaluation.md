# Coding agent foundations and evaluation

AI-authored engineering and learning packet for this hackathon profile. Proposed experiments are not measured outcomes. Keep the canonical [H0–H15 plan](../docs/02-mastery-learning-plan.md), current [H0 runtime packet](../study/packets/H0-reference-runtime.md), and [human tracker](../docs/05-mastery-tracker.md). The product can be built before human mastery; predictions and teach-backs still belong to Huy.

## First principle one Conditional generation is not execution

A decoder predicts the next token from its supported context. For output tokens `y1..ym` and input x, `p(y|x)=product_t p(y_t|x,y_<t)`. A tool-call JSON string is one possible generated sequence. Sampling a string neither opens a file nor creates a process. The adapter parses complete bytes; the controller checks authority and budget; the broker performs an admitted operation; a result becomes a new observation for the next model request.

The loop is therefore `observation -> proposal -> validation -> authorized effect -> receipt -> new observation`. Model state, workspace state, authority state and verifier state are different. This distinction remains true even if the model writes an eloquent explanation or generated code looks correct. Verification is an observation about a specified candidate, not proof for every possible input.

**VI:** Model giống người đề xuất hành động qua một cửa sổ hữu hạn. Program thật mới là người mở file và chạy test. Mỗi observation có identity; nếu file đã đổi thì model đang nhớ nội dung cũ dù conversation vẫn còn câu “tôi vừa đọc file”.

## First principle two The interface changes the work the model can do

SWE-agent studies the agent-computer interface, including bounded navigation, search, edits and concise feedback. Its mechanisms motivate small read/search/digest-checked edit/test tools, but its reported benchmark score is not a measurement of our harness or Nemotron. [SWE-agent paper](https://arxiv.org/html/2405.15793v3).

An unbounded repository dump consumes context without guaranteeing useful evidence. An unrestricted shell increases both action ambiguity and containment requirements. Our initial interface uses allowlisted text files, bounded search results, exact read digests and a fixed test recipe. A failed edit returns a stale-read error with a next useful observation; a failing test returns concise actual/expected behavior. Tool descriptions explain semantics rather than encourage arbitrary execution.

Tiny example: model reads `calc.py` at digest d0. A concurrent update creates d1. The model's replacement expecting d0 fails before changing bytes. The distinguishing test is not simply “edit succeeds”; it is “stale edit cannot overwrite d1, while a fresh read can produce a new proposal.” An independent behavioral assertion catches `return a+b+1` even if the visible test list is altered.

**VI:** Tool interface giảm số bước suy đoán model phải làm. Digest không giúp model thông minh hơn; nó làm effect an toàn khi model suy đoán từ dữ liệu cũ. Feedback tốt cho model biết lỗi ở boundary nào và đọc gì tiếp.

## First principle three Compute context and money are finite

For turn t define input tokens P_t, cached subset C_t, output tokens O_t, and per-million-token dollar rates r_i, r_c, r_o. Then `cost_t=((P_t-C_t)*r_i+C_t*r_c+O_t*r_o)/1_000_000`. Reasoning tokens already inside O_t must not be added again. All turns, test repairs, reviewers, routers and retries contribute to total cost. A multiworker design that pays twice for the same prompt does not earn a free gain from parallelism.

Worked synthetic example, not a provider price: P=1000, C=200, O=100; rates $1/$0.25/$3 per million. Cost is `(800*1+200*.25+100*3)/1e6=$0.00115=1150 micro-USD`. Billing1000 uncached plus200 cached would overcount. Internally use integer micro-USD rates and ceiling division to avoid float-rounding under-reservation. If cache discounts are unknown, freeze the undiscounted cache rate rather than invent a saving.

A conservative request reserve is `ceil((I_bound*max(r_i,r_c,r_write)+O_bound*r_o)/1e6)` with rates in micro-USD per million and bounds in tokens. Units reduce to micro-USD. The bounds must be enforced and source-backed; request bytes are not an exact tokenizer count. When response usage exceeds approved bounds, retain actual evidence, revoke the run and diagnose infrastructure/configuration. When usage is missing, preserve liability.

**VI:** Giá thấp mỗi token không đảm bảo task rẻ. Nếu context tích lũy qua nhiều turn hoặc retry sau crash, tổng input có thể lớn hơn dự đoán. Cần đo toàn bộ run, không chỉ turn cuối; Unknown cũng chiếm budget dù chưa có hóa đơn cuối.

For a serial turn, an approximate latency decomposition is `L_t = L_queue + L_network + L_prefill(P_t,C_t) + O_t / throughput_decode + L_tools + L_journal`. All terms use seconds. Measure from the same start/end boundaries, not just token streaming. A cache hit reduces some prefill work; a tool gap may evict it. Long reasoning may dominate latency even when the edit is only one line. Account rate limits and queueing can dominate over Python runtime overhead.

If fraction f of task time is genuinely parallelizable, the ideal compute-only speedup with N workers is `1/((1-f)+f/N)`. For f=.6 and N=2, the upper bound is1.43 before integration, coordination and verification overhead. Quality adds correlated proposals and conflict risks. The independence expression `1-(1-p)^N` only applies to independent success attempts with a suitable selection oracle; shared model/context bugs and additional cost violate the simple interpretation. Our default should change only after a matched experiment.

**VI:** Hai agent không tự làm task nhanh gấp đôi. Chúng có thể cùng mắc một lỗi và vẫn cần một verifier nối kết quả. Chạy nhiều sample rồi chọn đáp án tốt nhất phải tính tiền mọi sample và biết selector có quyền thấy gì.

## First principle four Model hardware facts do not replace product evidence

NVIDIA's Super card describes a hybrid Mamba-2/attention/LatentMoE model with120B total and12B active parameters. Active parameters relate to per-token compute, while total expert weights still matter for memory placement, bandwidth and serving. This is reported model information; we do not control or profile Token Factory's internal kernels/parallelism. [NVIDIA Super card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16).

For an ordinary attention layer reference, Q has shape `[B,H_q,T,d]`, K/V `[B,H_kv,S,d]`, grouped heads map `h_kv=floor(h_q/(H_q/H_kv))`, scores have shape `[B,H_q,T,S]`, and weighted values return `[B,H_q,T,d]`. A conventional KV footprint is `2*B*S*H_kv*d*bytes_per_element` per such layer. It is not a complete memory formula for a hybrid Nemotron deployment. The current compute workbench can teach indexing, masks and cache bytes on CPU; local CUDA absence means no NVIDIA GPU latency claim.

The hackathon's measurable boundary is application-level queueing, model request latency/usage, tool work and exact repair outcome. Training, custom kernels and a dedicated inference stack can become later capstone research when a measured bottleneck justifies them. H12/H13 understanding helps avoid false claims; it need not block the API-backed repair product.

**VI:** “12B active” không nghĩa cả model chỉ cần bộ nhớ của12B weights. MoE chọn expert để giảm compute nhưng expert vẫn phải có nơi lưu/đọc. Ta dùng API nên biết latency/usage bên ngoài, chưa biết GPU kernel hoặc residency bên trong provider.

## First principle five Evaluate the result and preserve every assignment

SWE-bench frames issue-conditioned repository repair rather than standalone function generation. Its methodology motivates a frozen base, issue, patch and regression checks; it does not make our six-task pilot an official SWE-bench score. [SWE-bench paper](https://arxiv.org/abs/2310.06770). Its official harness also documents evaluation caching by run/instance identity, illustrating why a changed patch must receive fresh exact verification. [Evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/).

Primary hackathon pilot endpoint: independently verified exact-tree repair by the declared execution deadline. Track human acceptance separately. The existing evaluator's `accepted` predicate requires real review evidence and commit timing; do not populate fabricated review receipts or timestamps to repurpose it. Introduce a separately versioned verified-repair outcome bridge, or report the pilot descriptively until the bridge is valid.

Pre-register six supported issues from at least two repository families, two repetitions, two arms =24 assigned runs, conditional on authorized budget. Split calibration from evaluation: no prompt/tool changes after viewing held-out evaluation failures. Both arms use the same model, visible task context, tool/capability restrictions, final checks, total token/dollar/CPU/time ceiling and serial worker count. The baseline is a minimal single-agent loop with the same safe tools; the candidate adds durable evidence and supported recovery. Any planner/router/reviewer calls count against the candidate's same ceiling.

**VI:** Baseline phải đủ tốt để kết quả có ý nghĩa. Nếu baseline dùng model rẻ hơn hoặc không được test trong khi candidate có thêm budget, ta đang đo nhiều thay đổi cùng lúc. Accepted của human và verified của grader cũng là hai endpoint khác nhau.

Freeze baseline restart semantics before assignments. Both arms share the trusted capability restrictions, physical-resource controller and outer budget meter that survives the killed process. Baseline B0 retains its latest known workspace and receipts but loses its volatile model conversation; it restarts a fresh session with issue plus current files and must pay for any new inference. Candidate D1 additionally restores its committed native transcript/evidence checkpoint under fresh authority. Neither arm may repeat an unresolved effect, reset the spending meter or regain spent tokens. This isolates persistent conversation/recovery, rather than comparing safe tools against an unsafe baseline.

For three predeclared task pairs inject one interruption in both arms at the common observable boundary after all tool results are known and before the next dispatch; D1 must also have committed its checkpoint there. Do not require B0 to have a checkpoint it does not implement. Report uninterrupted and interrupted strata separately; they use different task sets, so do not infer a clean causal effect of interruption across those sets. To study interruption itself, add within-task clean/fault assignments and include their added budget. Randomize arm order within task/repetition blocks. Unknown/infrastructure failures remain in the assigned denominator, with their category and exposure.

Publish per-assignment results: frozen task/base/model/config; verified success/failure; candidate and verifier identity; wall time; all-role input/cache/output tokens; settled and unresolved money; worker-test count/CPU; recovery time; duplicate external requests; regression/control outcome; optional reviewer effort actually observed. Record technical failure separately without hiding it from success rate. Report task/repository pairing; six tasks and two families support a descriptive pilot, not broad superiority or precise population confidence.

The scalar success rate is `resolved_assigned / all_assigned`. Also show median and tail latency with the measurement population clearly named; success-only latency should be labeled and cannot stand for all runs. Unresolved cost is not zero cost. Total infrastructure cost may remain only partially measured; distinguish provider token charge from hosting/CPU/storage and human time.

**VI:** Giữ failure trong denominator vì đó là trải nghiệm người dùng thực. Nếu chạy10 task nhưng chỉ báo5 task pass và thời gian của5 task đó, người xem không biết một nửa bị timeout hoặc thiếu budget. Pilot nhỏ nên đưa bảng từng task để judge tự kiểm tra.

## Discriminating controls and predictions

| Mechanism | AI-authored prediction before experiment | Observation that falsifies it |
|---|---|---|
| Complete-call admission | Truncated response with plausible tool JSON executes no edit | Workspace changes despite finish=length |
| Independent billing | Valid usage in semantically rejected response settles once | Charge disappears or replay charges twice |
| Native continuation | Next request retains assistant tool IDs/opaque supported fields and linked results | Coerced Anthropic blocks or missing reasoning field |
| Exact-tree verification | A result for tree A cannot publish review for modified B | Old receipt authorizes B |
| Clean checkpoint | Restart restores exact state with fresh owner and no replayed known effect | Old owner writes or known effect executes again |
| Ambiguous dispatch | Lost response retains bound and blocks implicit retry | A second identical HTTP request is sent or exposure released |
| Useful repair | New live runner repairs a held-out supported bug without oracle access | Runner consumes reference patch or unchanged/wrong controls pass |

These are test hypotheses from AI design, not Huy's predictions. After each experiment reconcile equation, state trace, inspected source and measured report; keep negative results. If the live loop fails, change one identified bottleneck on calibration tasks before reevaluating under a new frozen version.

**VI:** Prediction giúp test phân biệt cơ chế chứ không chỉ đếm pass. Human mastery cần em tự dự đoán case chưa xem, giải thích sai khác và transfer sang điều kiện mới; bảng AI viết không được ghi thành evidence của em.

## Learn from the delivered implementation

| Existing module | Hackathon reading question | Evidence to produce later |
|---|---|---|
| H0–H1 boundaries/loop | Which object and owner change at every arrow? | Reconstruct one exact live trace |
| H2 wire protocol | Why is a completed byte body different from a valid executable call? | Diagnose malformed JSON/finish/linkage |
| H3/H7 tools and containment | What authority can a tool exercise, and where does code run? | Reject stale/path/forged-pass cases |
| H4 budgets/recovery | What remains reserved after an uncertain response? | Predict clean vs advanced-frontier restart |
| H5/H6 context/retrieval | Which observation is current and what is retained exactly? | Trace digest freshness and native continuation |
| H8 evaluation | Which result is verified and which is human accepted? | Explain assigned denominator and fair baseline |
| H9/H11 product/service | Can another person reproduce and inspect a run? | Fresh-build and judge-access evidence |
| H10 multiagent | Does another worker help under the same ceiling? | Optional paired measured comparison |
| H12/H13 inference/serving | Which latency term and memory fact do we actually observe? | CPU trace now; hardware measurement only when available |
| H14/H15 training/capstone | What remains outside this submission and what result transfers? | Bounded research memo, not an invented training result |

Next human exercise after S0: predict a response containing valid usage but `finish_reason=length` and a complete-looking edit call. Trace stored bytes, spent/reserved money, workspace digest and replay request count before reading the recorded test result. Then transfer to a valid response whose effect occurs but tool receipt is lost. Keep Huy's answer in a genuine session record when he supplies it.


## Readiness evidence versus capability — 2026-10-11

[Current source checks](../research/system-readiness-plan-2026-10-11.md) exercise exact skills continuation, atomic service admission and per-instance Docker retirement. These strengthen durability mechanics without changing the fixed live B0/D1 experiment, population or denominator. The trusted RMSNorm probe supplies no CUDA result here and is outside required hackathon inference. Keep live-model scores, resource-matched comparisons, GPU measurements and human mastery unmeasured until their own experiments run.
