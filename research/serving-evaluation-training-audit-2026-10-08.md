# Serving, evaluation, and training: evidence audit and mastery path

Audit date: **2026-10-08, Asia/Ho_Chi_Minh**. Scope: the two preserved originals in `../archive/`, especially the mastery plan's equations E1–E7 and the research report's serving, evaluation, and RL sections. This is a selective, substantive audit, not certification of every citation. Public pages were opened during this audit; a live page is not a historically archived snapshot. Arithmetic below was independently recomputed on CPU. No GPU benchmark, vendor API experiment, or RL training was run.

**VI:** Mục tiêu là phân biệt ba việc rất khác nhau: nguồn thực sự nói gì, phép tính có đúng không, và hệ thống của mình có đạt kết quả đó không. Việc mở được bài báo chỉ xác minh phát biểu của tác giả; chưa tái lập thực nghiệm và chưa chứng minh hiểu hệ thống.

## 1. What survived verification, and what needs qualification

| Claim in originals | Audit result | Primary evidence and limit |
|---|---|---|
| Opus 5.5 input/write/read/output prices are $4/$5/$0.20/$20 per million tokens | **Verified as reported**, current public pricing | [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing). Fable 5.1 and Sonnet 5.5 are also present. These names should not be dismissed merely because they are unfamiliar. |
| Preserved thinking can reject prefix edits | **Verified, provider-specific** | [Preserved thinking](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking). Model/account compatibility and request type matter; it is not a universal law of all LLMs. |
| Qwen3-Coder-480B has 62 layers, 8 KV heads, 128 head dimension | **Verified configuration** | [Qwen config](https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct/blob/main/config.json). This gives 253,952 bytes/token for an ideal bf16 KV representation, not full runtime memory. |
| Kimi-K3 and DeepSeek-V4-Pro configs exist | **Verified existence; partial inspection** | [Kimi config](https://huggingface.co/moonshotai/Kimi-K3/blob/main/config.json), [DeepSeek config](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813/blob/main/config.json). The exact engine row layouts, replicated memory, and capacities were not rerun here. |
| Infrastructure can move Terminal-Bench scores by 6 percentage points | **Verified author report** | [Anthropic experiment](https://www.anthropic.com/engineering/infrastructure-noise), February 5, 2026. Same model/harness/tasks, different allocation policies; do not treat this as an independent Gaussian noise term. |
| Polar improves Qwen3.5-4B from 3.8% to 26.4% in Codex and 29.8% to 34.6% in Claude Code | **Verified author report** | [Polar Table 1](https://arxiv.org/html/2605.24220). It supports harness adaptation; it does not prove the gain transfers to arbitrary production work. |
| Composer 2 is trained using its deployed harness | **Verified author report** | [Composer 2 §1 and §4](https://arxiv.org/html/2603.24477v2). The report identifies Kimi K2.5 as its base. |
| Mooncake raises cache hits 1.7%→92.2%, throughput 3.8×, and reduces median TTFT 46× | **Verified benchmark report** | [vLLM × Mooncake](https://vllm.ai/blog/2026-05-06-mooncake-store), May 6, 2026. Specific Codex-derived workload, Kimi-2.5 NVFP4, 12 GB200 GPUs, 1P1D topology. |
| PPD cuts later-turn TTFT by about 68% | **Verified abstract claim** | [PPD v2](https://arxiv.org/abs/2603.13358v2), May 5, 2026. The authors explicitly say no fixed routing policy satisfies all SLOs. |
| LEGO-RL and Tmax papers exist | **Verified existence only** | [LEGO-RL](https://arxiv.org/abs/2608.17393), [Tmax](https://arxiv.org/abs/2606.23321). Their detailed numerical claims were not checked in full text in this audit. |

**VI:** Đừng gộp nhãn “reported” thành “measured by us”. Đặc biệt, 46× TTFT là mức cải thiện so với baseline có cache rất kém trên một workload cụ thể; hệ thống đang có cache tốt không có lý do tự động nhận thêm 46×.

## 2. The most important conceptual repair: three distinct invariants

The originals collapse three different requirements into one exact-prefix invariant. Separate them:

1. **State/recovery:** preserve an immutable event history sufficient to reconstruct decisions, attempts, tool results, and committed effects. The model-visible context can be a derived projection of that history.
2. **Cache compatibility:** reuse KV only when it represents the same model computation under a compatible identity: weights/adapters, token IDs, positions, attention semantics, modalities, and relevant runtime/cache namespace.
3. **Training fidelity:** record the actual state/action pair and behavior-policy probability for each sampled action. The next state may legitimately involve compaction, retrieval, or a changed context. RL does not require all requests to share one growing prefix.

An append-only transcript is a useful default, not the definition of an agent. Branching, rewinding, compaction, and policy changes can be explicit, valid state transitions. [vLLM's cache design](https://docs.vllm.ai/en/latest/design/prefix_caching/) includes parent hashes, exact block token IDs, and extra identities such as adapters, multimodal input hashes, and cache salts. It caches full blocks. Therefore the phrase “byte-identical iff reusable” is too strong: JSON whitespace is not model token identity; a matching prefix alone does not guarantee residency, routing, or compatibility; and specialized cache transformation methods need their own proof.

**VI:** Event log giống sổ cái, prompt giống bản báo cáo lấy từ sổ cái, KV giống kết quả tính trung gian của bản báo cáo. Sửa prompt không đồng nghĩa làm sai sổ cái; nhưng dùng lại KV của prompt cũ cho prompt mới có thể làm sai phép tính. Khi học RL, mỗi action phải khớp với đúng state lúc nó được sinh, chứ không bắt mọi state phải là phần mở rộng của state trước.

For a deterministic causal full-attention transformer with fixed weights and execution semantics, unchanged token and position prefixes are sufficient for semantically valid prefix KV reuse. Changing position j generally changes later states; it does not mathematically guarantee every later element changes. Bitwise reproducibility further depends on kernels, precision, batch shape, and reduction order. Sliding attention and recurrent models have different dependency and storage structures. A provider's signed reasoning binding is an API contract layered over these mathematics. Preserve returned opaque blocks as structured data; do not translate their semantics into another provider's schema by guesswork.

**VI:** “Tổng quát có thể thay đổi” khác với “mọi phần tử chắc chắn thay đổi”. Đây là thói quen tư duy quan trọng: chỉ khẳng định đủ mạnh để thiết kế đúng cache key và kiểm thử, không biến trực giác thành định lý sai.

## 3. Corrected cost, compute, and memory ledger

### 3.1 Billing is not FLOPs

The originals' E1 sums are correct under their stated constant-growth model:

\[
C_t=P+(t-1)\Delta,\quad \sum_{t=1}^{N}C_t=NP+\Delta N(N-1)/2.
\]

For a billing scheme that writes the first P tokens then writes each increment, total writes are `P+(N−1)Δ` and reads are `(N−1)P+Δ(N−1)(N−2)/2`. With `P=20,000`, `Δ=3,000`, `N=100`, writes are 317,000 and reads 16,533,000. At the verified Opus 5.5 rates, cached input costs **$4.8916**, versus **$67.40** uncached; 44,400 output tokens add **$0.888**. These are mathematical examples, not measured sessions. Different APIs classify tokens differently; generated tokens may already have resident KV, so “billed cache write tokens” is not a universally exact count of fresh prefill computation.

**VI:** Hóa đơn là quy ước kinh doanh, FLOPs là phép tính thực sự. Cùng một token có thể bị tính tiền ở lần đọc tiếp theo dù GPU không tính lại toàn bộ hidden state của nó. Không được lấy số token trong hóa đơn nhân một hằng số rồi coi đó là profiler.

Use the actual usage ledger:

\[
\text{USD}=p_u U+p_{w5}W_5+p_{w60}W_{60}+p_r R+p_o O+C_{tools}+C_{sandbox}+C_{storage}.
\]

Prices here are dollars/token, all token counts are provider-metered categories, and output includes billed hidden reasoning where applicable. Add retries, fan-out, and failed attempts. For cache write multiplier `a` and read multiplier `b`, n subsequent reuses break even when `n≥(a−1)/(1−b)`. Integer reads matter. The original omits **Sonnet 5.5** from the current 0.05× read multiplier exception. Cache misses can be partial; replace the binary all-or-nothing miss approximation with measured reused/written/uncached token counts in production.

**VI:** Đo cache theo phần prefix được dùng lại, không chỉ “request hit/miss”. Một request hit 1K token trong tổng 100K token khác rất xa hit 99K, dù dashboard nhị phân có thể ghi cả hai là hit.

### 3.2 Fix E3's limiting case and latency interpretation

For a conventional full-attention decoder, u newly prefetched tokens attending to C prior tokens have an approximate forward cost

\[
F(u,C)\approx2N_{active}u+4L H_q d_h\left(Cu+\frac{u(u+1)}2\right).
\]

The pair count sums `C+1, …, C+u`. The factor four accounts for QK and AV with a multiply-add counted as two FLOPs. Projection/MLP and expert terms are approximated by the first term; softmax, normalization, routing, communication, and implementation padding need separate treatment. **At C=0 the quadratic attention term remains.** The original's “C=0 → usual 2Nu” is only an approximation when attention is negligible, not a limiting identity. For a cold comparison, use `F(C+u,0)` versus `F(u,C)`, not inconsistent final context lengths.

**VI:** Cache bỏ việc tính lại token cũ, nhưng token mới vẫn phải đọc và attend lên token cũ. Prefill 1K token sau prefix 100K vì vậy khác prefill 1K token từ đầu. C=0 không có nghĩa attention biến mất: 1K token mới vẫn attend lẫn nhau theo causal mask.

Independent arithmetic with the original assumptions (`L=62,Hq=96,dh=128,Nactive=35e9,C=126180,u=857`) yields warm **3.906×10¹⁴ FLOPs**, cold at the same final length **3.348×10¹⁶ FLOPs**, ratio **85.71×**. This validates an arithmetic ratio, not an 85× wall-clock speedup. Assuming 40% of peak FLOPs does not establish achieved throughput. Use

\[
T\gtrsim\max(F/R_{achieved},\ B_{HBM}/BW_{achieved},\ B_{network}/BW_{network})+T_{unhidden},
\]

with contention and overlap measured. End-to-end time is queueing + prefill/first-token latency + subsequent token intervals + tool/harness/transfer time on the critical path. If TTFT includes the first token, the remaining uniform decode term is `(O−1)×TPOT`, not `O×TPOT`. Hidden thinking and tool-argument completion affect when useful work begins. Report p50/p95/p99 and time-to-validated-patch, not only tok/s.

**VI:** 85× ít FLOPs không tự động nhanh 85× vì có thể đang chờ HBM, network, scheduler hoặc tool. Cũng không được cộng toàn bộ thời gian của các worker chạy song song: latency đi theo đường phụ thuộc dài nhất; chi phí thì cộng mọi worker.

### 3.3 Memory capacity is a ceiling, not a deployment promise

For ideal GQA KV, a per-layer tensor pair is `K,V: [B,T,Hkv,dh]`; bytes are `2×L×B×T×Hkv×dh×bytes_per_element`. The verified Qwen dimensions give **253,952 bytes/token = 248 KiB/token** and **32.0437 GB at 126,180 tokens** for one sequence. These bytes exclude block rounding, scales, model weights, speculative buffers, graph captures, activation workspace, and allocator behavior. Architectures using compressed latent KV or recurrent state require their actual engine layout, not merely a name-based formula.

**VI:** “Active 35B” dùng để ước lượng compute mỗi token, còn 480B tổng tham số quyết định phần lớn dung lượng weight. MoE không tự nhiên chỉ cần bộ nhớ của active parameters; expert chưa được dùng ở token này vẫn phải nằm đâu đó hoặc được chuyển vào.

The original pooled arithmetic reproduces **2.945** Qwen 100K sessions on 8×80 GB and **31.927** on 8×180 GB with its assumed weight/reserve values. If using those assumptions literally, integer simultaneous complete sessions are at most **2** and **31**, before growth headroom. “About 3 sessions” risks rounding upward past OOM. The correct feasibility gate is per rank:

\[
W_r+A_r+G_r+S_r+K_r(N,T)+R_r\le H_r\quad\text{for every rank }r.
\]

`W` weights, `A` activation/workspace, `G` graph buffers, `S` recurrent/speculative state, `K` KV, `R` reserve. Tensor/expert/pipeline/data parallel layouts determine sharding and replication; a summed node budget can hide one rank's bottleneck. Then validate throughput and tail latency under arrivals, cache eviction, and long outputs. Separate **resident idle sessions**, **active decode sequences**, and **sessions meeting an SLO**.

**VI:** Tổng VRAM đủ không đảm bảo từng GPU đủ. Và đủ bộ nhớ cho 100 session đứng yên không đảm bảo trả lời 100 session trong thời gian mong muốn. Capacity planning phải có cả bản đồ placement và thử tải.

### 3.4 Correct the tiering economics inference

If B is bytes, τ is hours, and c is dollars/GB-hour, holding cost is `(B/10^9)×τ×c`. The originals omit these unit conversions in the displayed formula. Comparing full GPU rental attributed to HBM against raw amortized DRAM purchase cost is not an apples-to-apples production cost model: include hosts, network, power, operations, occupancy, replication, and opportunity cost. DRAM does not “always win”; fetch latency, contention, hit probability, and eviction of more valuable sessions matter. A provider's TTL and price alone cannot reveal its physical KV tier or margin.

**VI:** TTL 5 phút là hợp đồng sản phẩm, không phải bằng chứng KV nằm trong HBM đúng 5 phút. Chọn giữ hay tính lại cần phân phối thời gian quay lại, xác suất hit và chi phí cơ hội, không chỉ giá RAM/GB.

## 4. Evaluation corrections that change decisions

The current [Terminal-Bench 4.0 page](https://snorkel.ai/leaderboard/terminal-bench-4-0/) contains the five numerical rows quoted in the original. However, “the top five overlap within their intervals” is false: Opus 5.5 gives `[61.7,67.9]`, while GPT-6 Astra gives `[55.4,61.0]`. Even interval overlap is not a paired significance test. Verify what the intervals estimate before interpreting them, and obtain task-level paired outcomes. The [Composer 2 v2 report](https://arxiv.org/html/2603.24477v2) expressly says Anthropic Terminal-Bench rows use official Claude Code leaderboard scores; the original's attribution of the 58.0 versus 65.4 comparison to “Cursor harness versus native harness” is unsupported by that version's caption and accompanying text.

**VI:** Đọc chú thích bảng quan trọng hơn đọc con số. Hai cột khác nhau không nhất thiết là thí nghiệm chỉ thay harness; nếu điều kiện khác, không thể gán chênh lệch cho một nguyên nhân.

For task j with independent identical attempts of success probability `p_j`, `pass@k_j=1−(1−p_j)^k` and `pass^k_j=p_j^k`. Average these across tasks. Applying either function to the global mean p is generally wrong: task difficulty is heterogeneous and retries may be dependent or adaptive. For n sampled candidates with c successes on one task, the usual unbiased pass@k estimate is `1−choose(n−c,k)/choose(n,k)` for `n≥k`. A 75% fixed-p example yields 98.4375% pass@3 and 42.1875% pass^3. Distinguish “one of k attempts works” from “all k attempts work” in the product requirement.

**VI:** Nếu một nửa task luôn thành công và một nửa luôn thất bại, pass@3 vẫn chỉ 50%, không phải 87.5% tính từ p trung bình=0.5. Chạy thêm không cứu được task mà hệ thống chưa có năng lực giải.

`SE≈sqrt(p(1−p)/n)` is an IID Bernoulli approximation. Repeated runs, related tasks, repository clusters, and a fixed suite versus a sampled task population change the estimand. [Anthropic's statistical guide](https://www.anthropic.com/research/statistical-approach-to-model-evals) supports paired comparisons, within-task resampling, and clustering at the unit that creates dependence. It does not make “2 percentage points always require 2,400–8,000 tasks” universal: with 731 paired tasks and 14 improvements but zero regressions, the exact symmetric discordance null has two-sided p=`2×0.5^14≈0.000122`; population representativeness still requires justification. Power depends on discordance, not just marginal scores. Infrastructure differences may be systematic bias or change the task itself, rather than independent noise that disappears with trials.

**VI:** “Không đủ power” là phát biểu dựa trên giả định về variance và correlation. Nếu hai hệ thống giống nhau gần như mọi task và thay đổi chỉ sửa đúng một lớp lỗi, paired test có thể mạnh hơn rất nhiều. Đồng thời, tăng số lần chạy trên cùng repo không tạo thêm repo độc lập.

The research report's illustrative statement “0.1% per attempt becomes about 5% after 100” also needs correction: under independent constant-risk attempts it is `1−0.999^100≈9.52%`. Adaptive attempts need an explicit conditional-risk model; independence is not guaranteed. For evaluation, preregister how to count infrastructure faults, timeouts, cheating attempts, unavailable tools, and retries. Do not silently discard the hard cases. Report both unconditional user-visible success and conditional capability metrics, with denominators and retry costs.

**VI:** Tách lỗi hạ tầng để chẩn đoán là đúng; xóa mọi lỗi hạ tầng khỏi mẫu rồi quảng cáo reliability là sai. Người dùng vẫn chịu hậu quả của request không hoàn thành.

## 5. Multi-agent and RL: evidence without overgeneralization

[Anthropic's multi-agent research report](https://www.anthropic.com/engineering/multi-agent-research-system) reports roughly 15× chat token usage for its multi-agent workload and cautions that coding often has fewer parallelizable subtasks. Treat this as a measured property of that system and task mix, not a fixed tax for every subagent. Separate verifier roles can reduce self-evaluation bias, but a second LLM is not an independent ground-truth oracle. Shared models, prompts, evidence, and incentives create correlated errors. Compare single-agent, parallel-reader, and parallel-writer designs under matched dollars, model calls, and wall-clock budgets; include conflicts, duplicate work, and integration failures.

**VI:** Hai agent đồng ý không tạo ra hai bằng chứng độc lập nếu cùng đọc một nguồn sai. Giá trị của verifier đến từ quyền hạn khác, thông tin kiểm tra khác và phép kiểm tra có thể bác bỏ kết quả; không chỉ từ việc gọi một model lần hai.

A defensible RL sequence records `(observation_state, sampled_action_tokens, behavior_logprobs, masks, model_version, sampler_config, tool_result, reward_provenance)`. Mask environment output from the policy loss. Preserve boundaries and account for compaction branches. [Polar](https://arxiv.org/html/2605.24220) demonstrates proxy capture and token-faithful reconstruction; its paper reports reward-hacking trouble for naive per-request credit broadcasting. The [pinned verl rollout-correction note](https://github.com/verl-project/verl/blob/8718ca30a3f002f93b7c4fd99b9b2506718681bc/docs/algo/rollout_corr.md) distinguishes rollout behavior, old trainer policy, and current policy. Token-level clipping alone is not a proof that arbitrary trajectory/state-distribution mismatch is corrected.

**VI:** Training trace không chỉ là bản chat đã ghép lại. Nếu tokenizer ghép boundary khác, hoặc context đã compact, log-probability phải tương ứng state thực tế lúc sinh token. Sai denominator có thể tạo update nhìn hợp lý trong code nhưng tối ưu nhầm phân phối.

Study [Dr. GRPO](https://arxiv.org/abs/2503.20783) and [GSPO](https://arxiv.org/abs/2507.18071) as distinct objective choices, not interchangeable names for a universal recipe. For a group-centered advantage, group size one yields zero advantage under that construction; an alternative baseline changes that conclusion. Dropping all timeout/context-limit trajectories can change the objective and reward distribution. Router replay addresses an important source of MoE mismatch but does not remove weight staleness, sampling truncation, context transformations, or environment nonstationarity. Fast on-policy rollout refresh is a design tradeoff, not a mathematical requirement that every product redeploy every two hours.

**VI:** Chọn loss chỉ là một phần. Một reward có lỗ hổng sẽ dạy agent khai thác lỗ hổng nhanh hơn khi hệ thống training tốt hơn. Trước RL cần có grader sạch, dữ liệu provenance và một benchmark chuyển harness chưa dùng để train.

## 6. End-to-end minimum production system

A learning harness becomes a production service only after adding explicit ownership and recovery. Start with an authenticated API, a durable task/event store, an idempotent dispatch queue, worker leases, isolated execution environments, a model gateway with budgets and backpressure, artifact storage, structured traces, and an independent grading/review path. Store task/run/attempt/tool-call identities, permission decisions, side-effect status, model/harness versions, usage categories, and termination reasons. Lease expiry is not proof a tool had no effect; retries need effect-specific idempotency or reconciliation.

**VI:** Lỗi quan trọng nhất thường nằm ở ranh giới: tool đã ghi file hoặc gọi dịch vụ, nhưng worker chết trước khi ghi kết quả. “Retry” mù có thể thực hiện hành động hai lần. Event log phải phân biệt ý định, bắt đầu, kết quả quan sát và effect đã commit.

| Layer | Minimum experiment | Evidence gate |
|---|---|---|
| Request/control | Duplicate submit, cancel, restart, budget exhaustion | No duplicate task ownership; cancellation eventually stops model and tool work |
| Worker/tool | Kill worker before and after a write; hang subprocess; oversized output | Recoverable attempt state, bounded execution, no false success |
| Model gateway | Rate limit, stream interruption, provider fallback | Backoff/backpressure, retry cost recorded, served-model identity where observable |
| Context/cache | Edit old tool output, change adapter, compact, branch, expire cache | Correct request semantics; observed usage agrees with accounting |
| Evaluator | Alter tests, tamper logs, replay known patch, resource exhaustion | Held-out tests and clean regrade; explicit infrastructure outcome |
| Deployment | Deploy a new harness during a long run, then roll back | Active run version stays coherent; migration or drain policy explicit |
| Serving | Replay realistic arrivals and long-tail tool gaps | Quality plus p95 latency and dollars/resolved task meet declared SLO |

**VI:** Ban đầu API model là đủ để học đầy đủ control plane. Tự host GPU chỉ nên bắt đầu khi trace cho thấy vấn đề cần giải là serving hoặc khi mục tiêu nghiên cứu là inference/RL; không cần mua cluster để học recovery và permission đúng.

## 7. Ordered research and implementation path

Each step requires a prediction, a small reference, a failure-inducing test, and a measured artifact. Start from the smallest model/harness that permits the mechanism to be inspected; keep frontier-scale numbers as extrapolations until measured.

**VI:** Tài liệu đọc theo câu hỏi cần trả lời, không theo độ mới của tên framework. Mỗi bước phải tạo ra một dự đoán có thể sai, rồi dùng log hoặc kiểm thử để phân biệt nguyên nhân.

| Order | Primary reading | Build and falsification exercise |
|---|---|---|
| 1. Exact request semantics | [vLLM prefix caching](https://docs.vllm.ai/en/latest/design/prefix_caching/) and provider request/caching contracts | Render a 3-turn tool conversation; save token IDs and boundary metadata; vary one old token, tool schema, and image identity. Predict first invalid cache block. |
| 2. Cache memory and scheduling | [PagedAttention paper](https://arxiv.org/abs/2309.06180) and [Qwen config](https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct/blob/main/config.json) | Derive bytes/token; implement a CPU block-allocation simulator; compare predicted residency with an actual small-model engine run later. |
| 3. Multi-turn serving | [PPD v2](https://arxiv.org/abs/2603.13358v2), [vLLM × Mooncake](https://vllm.ai/blog/2026-05-06-mooncake-store) | Replay arrivals, append sizes, and tool delays; compare local affinity, load-only routing, and shared-cache policy. Make transfer cost visible. |
| 4. Evaluation validity | [Infrastructure noise](https://www.anthropic.com/engineering/infrastructure-noise), [Statistical approach](https://www.anthropic.com/research/statistical-approach-to-model-evals) | Freeze image/resources/tasks; paired harness A/B; save task-level outcomes and clustered intervals; include fresh private tasks. |
| 5. Multi-agent control | [Anthropic Research architecture](https://www.anthropic.com/engineering/multi-agent-research-system) | Single writer + independent readers first; deliberately introduce overlapping edits and compare cost/conflict/verified-success rates. |
| 6. RL foundations | [Dr. GRPO](https://arxiv.org/abs/2503.20783), [GSPO](https://arxiv.org/abs/2507.18071) | Hand-compute a two-action trajectory gradient; test environment-token mask, zero-variance group, truncation, and behavior/current mismatch. |
| 7. Harness-native RL | [Polar](https://arxiv.org/html/2605.24220), [verl correction](https://github.com/verl-project/verl/blob/8718ca30a3f002f93b7c4fd99b9b2506718681bc/docs/algo/rollout_corr.md), [Composer 2](https://arxiv.org/html/2603.24477v2) | Capture exact rollout tokens through a gateway, grade only the patch in a clean environment, train a small baseline, then test on an unseen harness. |

**VI:** Gate cuối không phải “đã đọc hết paper” hoặc “loss giảm”. Hãy giải thích được vì sao cache hit mà latency vẫn xấu, vì sao reward tăng mà private eval giảm, và vì sao thêm agent làm throughput công việc giảm. Đó mới là khả năng chuyển kiến thức sang hệ thống chưa từng thấy.

## 8. Provenance boundaries and unresolved work

The originals contain many `measured in clone` and pinned `file:line` claims. This audit did not recreate their checkouts or run their template experiments, so it does not promote those labels to independently reproduced. Before using an anchor in a lesson, resolve the commit, verify the line, inspect its caller and configuration, and execute the discriminating test. Live `main` configs should become revision-pinned artifacts with hashes when experiments begin. None of the source existence checks licenses claiming access to private Anthropic/Cursor infrastructure. Public design accounts are evidence about disclosed behavior; a reconstruction remains a reconstruction.

**VI:** Một link có commit hash tốt hơn link `main`, nhưng vẫn chưa đủ: dòng đó có thể là code không được gọi trong config đang học. Cần trace từ request qua dispatcher đến implementation, rồi đối chiếu output và profiler. Những phần chưa đo phải giữ nhãn “unverified”, không được biến thành năng lực mình đã làm chủ.
