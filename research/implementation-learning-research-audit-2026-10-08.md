# Implementation audit: learning, evaluation and tensor evidence

**Date:** 2026-10-08. **Author:** AI research audit. **Purpose:** turn the inspected learning/research contracts into an executable reference-code scope under Huy's current build-first request. Implementation authorization does not establish human mastery or authorize unspecified paid experiments. This audit changes no original sources, previous runs or learning evidence.

**VI:** Code được phép xây trước để làm vật thể học tập. Điều thay đổi là thứ tự delivery, không phải tiêu chuẩn evidence: phần AI viết, phần máy đo và phần Huy tự giải thích vẫn phải tách rõ.

## Inspected material and evidence status

Reviewed the five `docs/` chapters, H0 packet/session and study templates, README/START-HERE, the three existing research reports, prior delivery/role/design/context JSON verification records, source manifest, and the evaluation/role contracts in `capstone/03` and `capstone/06`. This is a cross-document implementation audit; it is not independent reproduction of every historical product benchmark. The earlier reports already correct exact-prefix overclaims, billing/FLOP conflation, evaluation denominators and unsupported proprietary-internals claims; retain those corrections.

**Measured in this audit:** all 18 successful source snapshots still match the SHA-256 identities in [the manifest](../references/source-manifest-2026-10-08.json). Read-only environment inspection found Darwin arm64, Python 3.11.7, PyTorch 2.7.1, `torch.cuda.is_available()==False`, `torch.version.cuda==None`, and MPS available. No tensor benchmark, GPU run, live model call, training run or service deployment was performed by this audit. MPS availability is not CUDA availability. Previous JSON verification records are historical scoped records, not present-tense implementation status; their differing effort estimates reflect successive documents.

**VI:** Hash khớp chỉ chứng minh snapshot còn nguyên. `torch` import được chỉ chứng minh thư viện có mặt; chưa chứng minh attention đúng hay kernel nhanh. Không sửa lịch sử để biến một delivery check cũ thành kết quả của code mới.

## Implementation interfaces to preserve

The following are **proposed modules/interfaces**, not existing file claims. Keep these close to the same durable identities used by the runtime, so reports cannot quietly invent a second source of truth.

| Module | Inputs and outputs | Distinguishing evidence |
|---|---|---|
| Frozen experiment manifest | Task/base/grader/config/resource identities, planned assignment rows, split, hypothesis, endpoint, cutoff, seed → canonical bytes and hash | Reject missing ceilings, duplicate assignment identity, unsupported profile/N or inconsistent grader/base before dispatch |
| Outcome and paired analysis | Full planned rows plus append-only outcome/review/settlement facts → all-assigned denominators, per-task paired differences, costs, completion curves and clustered uncertainty | Missing, infra-failed, deadline, cancelled and unknown rows remain nonaccepted at cutoff; zero accepted makes cost/acceptance undefined |
| Deterministic DAG/scaling experiment | DAG, durations, dependencies, aggregate capacity, N, policy, shared envelope → simulated event trace and critical path | Chain gets no worker-parallel speedup; independent branches expose concurrency; integration remains serial; retained slots remain occupied |
| Fixed-N allocation experiment | Static allowances or progress-aware decisions based only on observed state → previous/new allowances, reason and observation IDs | Redistribution cannot reclaim unknown billed liabilities; no future completion signal may enter a decision |
| Evidence report | Requirement/DAG/ownership/action/receipt/tree/verifier/review identities → compact readable reconstruction with original event pointers | Successful and rejected/stale/unknown branches remain traceable; missing evidence produces unknown, never an inferred success |
| Serving replay | Fixed arrival times, prompt/appended tokens, output lengths, tool gaps, cold/warm state, capacities and policy → explicit simulated queue/cache/service timeline | Open-loop arrival generator keeps sending during overload; report rejection and failures alongside quantiles |
| Tensor reference and ledger | Tiny deterministic Q/K/V, head mapping, absolute positions → scores, mask, probabilities, outputs, shape/stride/dtype/device/byte metadata | Independent scalar reference, explicit GQA expansion, cached-prefix equivalence, future-token perturbation and malformed shapes |
| KV/cache calculator | Explicit L/B/T/Hkv/dtype/layout/block/model/config identities → ideal bytes, rounded blocks, hits/misses/evictions | Wrong KV head count, changed prefix/adapters/namespace, pinned blocks under pressure; no inference that calculated bytes equal runtime capacity |
| Offline trajectory validator | Actual sampled IDs, observation tokens, masks, behavior/current logprobs, versions and reward provenance → validation and small masked objective | Observation/padding excluded; mixed versions and mismatched lengths rejected; zero-action masks and zero-variance rewards handled explicitly |
| Optional CUDA benchmark | Pinned environment, device/backend/dtype/shapes, warmup/repeats, correctness tolerance → raw timings and capability status | CUDA unavailable must emit `skipped`; available CUDA requires synchronization/events and declared timing boundary |

**VI:** Đây là các dụng cụ để đo và trace cùng một hệ thống. Scheduler simulation không nên xuất một cột “coding accuracy” tưởng tượng. Tensor reference cũng không phải một model đã train; nó kiểm tra đúng phép tính attention và đúng cách đếm bộ nhớ.

## Research contract that code must not weaken

Preserve three distinct arm identities: bare single-agent A, coordinated candidate N=1, and coordinated candidate N=2/4. Production defaults to two patch workers; a research profile validates only 1, 2 or 4, and actual dispatch remains gated on declared execution capacity and isolation/recovery evidence. A deterministic simulator may explore the mechanics without asserting that those deployment gates passed. Coordinator, integration, retries, verification, failed branches and cleanup all consume the common envelope. Model-call concurrency and physical sandbox slots are separate resources.

The existing diagnostic plan remains 36 tasks × 3 trials × 2 arms = 216 attempts, with six separate calibration controls. Code may generate and validate the assignment table without claiming those real tasks or attempts exist. No repository commit, hidden grader, live-model success or powered sample size may be fabricated. Compare allocation at one frozen N after the scaling development study; held-out confirmation remains separate. The empirical role concerns team size, budget, horizon, surprising failures and readable research tooling, as [the official role posting](https://job-boards.greenhouse.io/anthropic/jobs/5442680008) currently describes. A four-worker fixture does not demonstrate large-team operational experience.

**VI:** N=1 có coordinator vẫn có overhead nên không được đổi tên thành baseline thuần. Tăng N mà tăng cả tổng CPU/RAM hoặc ngân sách là đổi nhiều biến; có thể là experiment hợp lệ nhưng phải báo điều kiện đó, không gán toàn bộ gain cho teamwork.

For equal planned trials per task, compute `q_a = mean_t(mean_r(Q_tar))` and paired `delta = mean_t(mean_r(Q_tBr)-mean_r(Q_tAr))`. Preserve complete paired task blocks during bootstrap; use repository blocks when task dependence requires them. Tiny fixtures test arithmetic and missing-data handling, not confidence-interval coverage for real research. [Anthropic's statistical guide](https://www.anthropic.com/research/statistical-approach-to-model-evals) supports paired differences and dependence-aware uncertainty. Its [infrastructure experiment](https://www.anthropic.com/engineering/infrastructure-noise) reports resource-related outcome changes; resource limits therefore belong in the manifest, not an omitted implementation detail.

**VI:** Nếu B được giao 10 run và có 2 run lỗi hạ tầng, mẫu số vẫn là 10. Bootstrap 3 trial của cùng task như 3 task độc lập sẽ làm độ chắc chắn trông đẹp hơn thực tế. Khi chỉ có vài repo, phải nói rõ uncertainty ở cấp repo còn yếu.

## Exact tensor contract and the cached-decoding trap

Use the logical layout `Q[B,Hq,U,D]`, `K[B,Hkv,C+U,D]`, `V[B,Hkv,C+U,Dv]`, with `Hq % Hkv == 0`. Query head `h` reads KV head `floor(h/(Hq/Hkv))`. For a query at local appended index `i`, the allowed key indices are `0 <= j <= C+i`; score is the D-element dot product divided by `sqrt(D)`. The output is the softmax-weighted value sum. Every trace records whether head expansion is physical or a logical indexing rule; physical expansion is reference convenience, not proof that an engine allocates expanded KV.

The inspected [PyTorch 2.7 SDPA contract](https://docs.pytorch.org/docs/2.7/generated/torch.nn.functional.scaled_dot_product_attention.html) documents an upper-left causal bias for a nonsquare attention matrix and explicit dropout behavior. Consequently, a cached suffix must use an absolute-position Boolean mask with `is_causal=False`, unless the selected backend supplies a verified equivalent offset mask. Set `dropout_p=0.0` for deterministic reference comparisons; evaluation mode alone does not disable this function's dropout.

**VI:** Query mới ở vị trí 3 phải nhìn key 0,1,2,3. Nhưng một ma trận mask 1×4 lấy tam giác trên-trái chỉ cho nhìn key 0. Đây là lỗi semantics dễ bị che khi chỉ test prefill vuông mà chưa test decode với cache.

**Derived tiny distinguishing example:** `Q=[0]`, `K=[0,0,0,0]`, `V=[2,4,8,10]`, shapes `[1,1,1,1]`, `[1,1,4,1]`, `[1,1,4,1]`, and cached length `C=3`. All four logits equal zero. Correct probabilities are `[1/4,1/4,1/4,1/4]`, giving output `6`; an upper-left 1×4 causal mask gives `2`. This is a hand-derived prediction, not a measurement. Required test: compare explicit-mask SDPA and scalar reference against `6`, show that the intentionally wrong mask disagrees, then compare the suffix of cold full causal attention against cached appends for multiple C/U/head ratios and noncontiguous layouts. The test should detect a mask defect independently of its implementation.

**VI:** Ví dụ Q=0 cố ý loại mọi khác biệt dot-product để chỉ còn mask. Nếu expected output tự tính bằng cùng helper tạo mask thì test có thể cùng sai; giá trị 6 là oracle độc lập có thể tính tay.

Ideal GQA bytes are `2*L*B*T*Hkv*D*element_bytes`; with `L=2,B=1,T=4,Hkv=1,D=2,b=2`, this is 64 bytes. The currently inspected [Qwen configuration](https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct/blob/main/config.json) supplies a real-model comparison, but the moving `main` URL must become a revision/hash-pinned artifact before a reproducible model-specific experiment. Keep ideal KV, block rounding, model weights, activation/workspace, graph buffers, fragmentation, sharding/replication and reserved headroom separate. Summed GPU memory cannot establish per-rank feasibility or an SLO.

**VI:** Tensor ledger nên cho thấy từng số đến từ đâu: 2 là K và V, T là số token, Hkv không phải Hq. Khi tăng query heads mà giữ KV heads, score compute tăng nhưng ideal KV bytes không tăng theo cùng hệ số.

## Primary-source refresh and GPU boundary

| Inspected primary source | Supported conclusion | What remains unestablished here |
|---|---|---|
| [vLLM automatic prefix caching](https://docs.vllm.ai/en/latest/design/prefix_caching/) | Full-block hashes incorporate parent prefix, tokens and extra identities; blocks have ownership/reference counts and eviction state | Actual cache residency, speedup or compatibility of a particular installed engine |
| [PagedAttention paper](https://arxiv.org/abs/2309.06180) | Authors present paged KV memory management and evaluate their implementation | Independent reproduction or a speedup for this capstone |
| [PyTorch 2.7 SDPA](https://docs.pytorch.org/docs/2.7/generated/torch.nn.functional.scaled_dot_product_attention.html) | Tensor/mask/dropout/backend contracts relevant to installed PyTorch 2.7.1 | That a specific CUDA fused kernel is available or selected |
| [PyTorch CUDA semantics](https://docs.pytorch.org/docs/2.14/notes/cuda.html) | GPU execution is asynchronous; unsynchronized host timing is insufficient | CUDA performance on this Mac; 2.14 availability in the current interpreter |
| [NVIDIA asynchronous execution](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/asynchronous-execution.html) | Streams/events distinguish queued dispatch from completed device work | Achieved overlap, bandwidth or utilization on an unmeasured device |
| [NVIDIA kernel programming](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/writing-cuda-kernels.html) | Thread hierarchy and memory spaces support a concrete kernel trace | Exact CTA/warp/register/Tensor Core mapping of a library call without inspecting its selected kernel |

The PyTorch `stable` URLs currently redirected to 2.14 documentation while the local interpreter reports 2.7.1; versioned 2.7 SDPA documentation was separately opened for the implementation contract. An older NVIDIA guide URL returned 404; the current guide paths above were then located and opened. Neither freshness nor source existence is a performance ranking. No claim of “latest/best” stack follows from this audit.

**VI:** API Python không cho biết ngay warp nào xử lý output nào. Muốn đi xuống phần cứng thật cần backend/kernel được chọn, source tương ứng và profiler. Nếu chưa có GPU, ta có thể vẽ đường đi dự kiến nhưng phải ghi “proposed”, không ghi đã quan sát Tensor Core.

CUDA benchmark output should include device name/capability, driver/runtime/library versions, backend selection, seed, shapes/strides, input/accumulation dtype, correctness tolerance, warmup count, raw repeat timings, peak allocated/reserved memory and the scope of included transfers/compilation. Report a clear skip if unavailable. Explicit eager-reference allocations can be much larger than fused-kernel allocations; compare equivalent workloads and distinguish kernel-only from end-to-end timing. Hosted API timing cannot identify a provider's HBM traffic, kernel layout or actual GPU FLOPs.

**VI:** CPU reference có thể chứng minh output khớp phương trình; benchmark GPU mới đo được latency của một kernel trên một máy. Cả hai vẫn chưa chứng minh task coding tốt hơn nếu critical path chủ yếu nằm ở tool hoặc integration.

## Delivery acceptance and remaining evidence

The authorized reference implementation should provide real runnable code, deterministic counterexamples, readable raw traces, verified concept-to-code anchors and an explicit capability matrix. A CLI demo must identify synthetic timing/model behavior as synthetic. Optional backends should fail closed or emit a structured skipped result; they must not silently replace a missing GPU, sandbox, provider or distributed database with a simulator while preserving the stronger label.

This audit is **inspected/derived/proposed**, with measured environment and hash facts explicitly identified above. Follow-up implementation tests can upgrade only their exercised mechanisms to measured. Live coding quality, hostile-code containment, PostgreSQL/Temporal failure behavior, cloud recovery/SLOs, CUDA performance, training improvement, independent reproduction and Huy's mastery remain separate evidence requirements. Exact code anchors for new modules must be generated after implementation and line inspection; no future line numbers are invented here.

**VI:** “Whole reference codebase” nên nghĩa là mọi boundary có chỗ chạy/trace hoặc báo rõ backend còn thiếu. Không có nghĩa một buổi build đã biến fixture thành production service, cũng không biến phần giải thích AI thành teach-back của Huy.
