# GPU readiness audit — 2026-10-11

Status: **research and source inspection; no GPU execution**. This audit refines the existing NV-S0–NV-S4 sequence in [the reference specification](../capstone/07-reference-implementation-spec.md#ordered-implementation-slices). It introduces no second evaluator, benchmark population, billing service or production-readiness claim. Paid execution remains disabled.

The next useful implementation is a runnable, bounded **trusted RMSNorm CUDA probe**, together with explicit manifest and observation contracts. It can be prepared and adversarially tested on CPU now. Generated-candidate execution requires a separate device-only loading/supervision boundary; extending the existing Python verifier with `--gpus` would not establish that boundary. The proposed contract is [gpu-boundary-spec-2026-10-11.md](gpu-boundary-spec-2026-10-11.md).

**VI:** CPU đã định nghĩa kết quả đúng. Bước kế tiếp cần một chương trình có thể đem lên GPU thật để kiểm tra công thức, thời gian và vòng đời tài nguyên. Chạy code tham chiếu do repository sở hữu và chạy CUDA do agent sinh ra là hai mức tin cậy khác nhau; tài liệu giữ rõ ranh giới này.

## 1. Inspected project state and actual owners

The active state, H0 packet, reference specification, implementation coverage and recovery runbook were read. The following anchors were inspected on October 11; they describe the checkout before the proposed NV-S1 implementation.

| Boundary | Inspected source | Existing evidence and limitation |
|---|---|---|
| Numerical contract | [RMSNorm contract](../compute/rmsnorm.py#L21), [independent scalar reference](../compute/rmsnorm.py#L85), [comparison](../compute/rmsnorm.py#L124) | CPU FP32 inputs; unrounded Python-float/FP64 reference; fixed elementwise tolerance; input/output bytes bound. The observation has no executable provenance and grants no acceptance. |
| Existing CUDA preparation | [preflight](../compute/cuda_benchmark.py#L13), [attention benchmark](../compute/cuda_benchmark.py#L70) | Explicit unavailable status, CUDA events, correctness before timing, allocator baseline/deltas and per-sample output release. This is trusted attention code, not an RMSNorm/generated-kernel verifier. |
| Host execution lifetime | [bounded_process](../service/execution.py#L149) | Bounds process output/time and observes owned process-group retirement. This cannot prove escaped actors, remote effects or GPU work ended. |
| Container boundary | [DockerSandbox](../service/execution.py#L259), [launch flags](../service/execution.py#L347), [close](../service/execution.py#L468) | Pinned local image, no network/host mounts/credentials, read-only root, dropped capabilities, CPU/RAM/PID/tmpfs limits; immutable instance ID and creation nonce. There is no GPU UUID, VRAM mechanism, driver interface, profiling privilege or GPU health/retirement contract. |
| Authority and capacity | [attempt admission](../service/storage.py#L565), [trusted retirement transition](../service/storage.py#L1227) | Unretired environments occupy slots; unknown effects block replacement; retirement evidence enters through a trusted caller. A nonempty evidence object is not physical proof. GPU-specific evidence must be verified before reaching this transition. |
| Bounded repair | [PythonFunctionVerifier](../service/repair_verification.py#L268) | The supported intake/recipe is stateless Python function repair. It neither compiles CUDA nor owns a GPU measurement envelope. |

**VI:** Authority nằm ở RuntimeStore; tensor oracle chỉ biết bytes; supervisor biết process/container nào mình sở hữu. Không object nào tự suy ra phần còn thiếu. Đặc biệt, `retire_sandbox()` là nơi ghi nhận observation đã được tin cậy, không phải cảm biến đo GPU.

## 2. Primary-source findings checked on 2026-10-11

Sources were browsed on October 11. Versioned PyTorch 2.14 pages match the project's documented compute version. NVIDIA's current CUDA event page identifies API version 13.4; this does not upgrade the local lock or establish compatibility with a future worker. Latest documentation is a dated research input, not a pinned executable dependency.

| Source and observed version | What it supports | Consequence for this project |
|---|---|---|
| [PyTorch 2.14 RMSNorm](https://docs.pytorch.org/docs/2.14/generated/torch.nn.RMSNorm.html), [functional form](https://docs.pytorch.org/docs/2.14/generated/torch.nn.functional.rms_norm.html) | RMS normalization has an epsilon parameter and normalization shape; the default epsilon is dtype dependent. | Keep the existing explicit `epsilon=1e-5` and `[H]` normalization. Compare authored eager code with the library arm on exactly that contract. Do not inherit default epsilon. |
| [PyTorch CUDA semantics](https://docs.pytorch.org/docs/main/notes/cuda.html) | CUDA work is asynchronous; streams require ordering; allocated and reserved memory are different caching-allocator quantities. | Synchronize completion, identify the stream/device, retain allocation baselines and label allocator observations. CPU dispatch duration is not GPU execution duration. |
| [CUDA event management 13.4](https://docs.nvidia.com/cuda/cuda-runtime-api/cuda_runtime_api/group__CUDART__EVENT.html) | Elapsed time uses milliseconds, approximately 0.5 microsecond resolution; event completion and asynchronous errors need separate handling; other stream work can affect timing. | Reject zero/nonfinite/enqueue-only samples; use explicit synchronization and a quiet device; keep raw samples and scope labels. An elapsed-time value alone is not a successful completion receipt. |
| [PyTorch allocator fraction](https://docs.pytorch.org/docs/2.14/generated/torch.cuda.memory.set_per_process_memory_fraction.html) | The fraction limits the caching allocator and free memory may be below total capacity. | Do not label it a hard VRAM limit for arbitrary CUDA code. It can be an optional trusted-PyTorch diagnostic only. |
| [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html) | Device enumeration controls visibility; driver capabilities control mounted driver features; base images can default to all GPUs. MIG management requires additional privileged device exposure. | Select one immutable UUID, set explicit capabilities, reject inherited all-device/MIG-management settings. Container visibility is not exclusive scheduling or a VRAM quota. |
| [MIG guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/latest/index.html), [MIG technology](https://www.nvidia.com/en-us/technologies/multi-instance-gpu/) | Supported hardware can partition compute and memory resources with documented fault/QoS isolation. | A future partition recipe must bind physical UUID, instance identity/profile and supported hardware. The first implementation should use one dedicated physical GPU; do not pretend a generic Boolean implements MIG or hostile-code containment. |
| [NVIDIA nvidia-smi](https://docs.nvidia.com/deploy/nvidia-smi/index.html) | Recovery actions can require reset, drain or reboot; reset requires administrative conditions and may fail; health should be checked before reuse. | Timeouts/faults retain uncertainty. No automatic reset escalation. Record external recovery and fresh health observations before reuse. |
| [Nsight Compute profiling guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html), updated Aug 27, 2026 | Profiling can serialize kernels, change clocks and flush caches; replay changes workload conditions. | Diagnostic profiling and clean timing must be separate runs with configuration identities. A profiler duration is not automatically the component latency experienced by a consumer. |
| [Compute Sanitizer](https://docs.nvidia.com/compute-sanitizer/ComputeSanitizer/index.html), [limitations](https://docs.nvidia.com/compute-sanitizer/ReleaseNotes/index.html) | Memcheck, racecheck, initcheck and synccheck cover distinct defect classes; racecheck focuses on shared-memory hazards, and there are unsupported execution patterns. | Specify the tools, exercised launches and exit/log completeness. A clean run proves neither every race absent nor isolation. Missing execution coverage is invalid, not clean. |
| [CUDA Driver API](https://docs.nvidia.com/cuda/cuda-programming-guide/03-advanced/driver-api.html) | A trusted host can load CUDA modules and supply the launch configuration/arguments. | Prefer a future fixed device-only module interface; candidate code must not provide the measurement host, events, final expected values or receipt writer. Driver/compiler vulnerabilities remain in the worker threat model. |

**VI:** Một đơn vị đo hoặc API đúng chỉ giải quyết một lớp. CUDA event đo timeline thiết bị; `perf_counter_ns` cộng với synchronize đo thời gian gọi từ host. `memory_reserved` là phần allocator giữ lại, không phải tổng HBM mà mọi process sử dụng. Cần ghi rõ từng đại lượng để không so sánh các số có tên giống nhau nhưng ý nghĩa khác nhau.

### Authoritative GPU coding-evaluation patterns

Two repository heads were resolved with `git ls-remote`, then their raw pinned files inspected read-only. No repository code was installed or executed.

| Source | Pinned identity and relevant finding |
|---|---|
| [NVIDIA ComputeEval README](https://github.com/NVIDIA/compute-eval/blob/00fbad91b63957a002b501f33a06510cd25beaae/README.md) | Commit `00fbad91b63957a002b501f33a06510cd25beaae`; raw README SHA256 `7e6aabeb0459263f21c3c90ec653a05368edd244c33aa8080fcfb25a1af66a3b`. Separates build, correctness, optional timing/profiling; requires explicit execution mode. Raw lines 717–727 require sanitizer workload coverage through a hidden-harness side channel, reject candidate stdout as coverage proof and rerun normal correctness after sanitation. |
| [KernelBench timing implementation](https://github.com/ScalingIntelligence/KernelBench/blob/423217d9fda91e0c2d67e4a43bf62f96f6d104f1/src/kernelbench/timing.py) | Commit `423217d9fda91e0c2d67e4a43bf62f96f6d104f1`; raw file SHA256 `eaabdad5dd042cfaac7159713b5f0c17a9244e65622b504eb3ca909d780854c5`. Supplies distinct CUDA-event and synchronized-host timers. Timing backends differ in cache and warmup policy; the Triton interface ignores caller trial/warmup counts in favor of its own duration policy. |

The project adopts the **mechanisms**, not benchmark scores or a second harness. In particular, generated-program stdout cannot authenticate time or coverage. A public benchmark's model-visible/held-out convention does not protect a test harness from candidate host code once both are compiled into one process. The existing NV1 contract already requires the stronger boundary. KernelBench's reported benchmark success and external papers do not establish this project's capability.

**VI:** Có thể học cách họ đồng bộ, ghi sample và kiểm tra coverage. Không thể lấy tên một benchmark làm bằng chứng môi trường của mình an toàn. Trước khi tin receipt, phải biết bên nào được sửa code tạo ra receipt đó.

## 3. Prioritized findings

These priorities describe hazards at the proposed GPU extension boundary. They are not reports of demonstrated exploits in the existing, explicitly CPU/trusted-code paths.

| Priority | Finding | Required resolution and distinguishing failure |
|---|---|---|
| P0 | Unrestricted candidate Python/C++ host code in the measuring process can edit timing, outputs or report generation. | Trusted probe accepts no candidate input. Future generated path uses a fixed trusted launcher and device-only module; reject custom executable/shared-library/Python loaders. Forged stdout must never become a performance result. |
| P0 | Container/process disappearance does not establish GPU retirement after a fault or uncertain launch. | Preserve device-work Unknown and occupied reservation. Timeout + empty container inventory must still refuse automatic GPU reuse. |
| P0 | Host memory flags and PyTorch allocator limits are not a general VRAM quota. | First generated profile reserves a whole physical GPU's capacity and declares that mechanism. Reject a claimed smaller enforced quota without supported hardware isolation. |
| P1 | Existing attention benchmark provenance and order are insufficient for a generated RMSNorm performance claim. | New trusted probe binds source/config/input/device identities, paired arm ordering, A/A observations, component/device scope and post-timing correctness. Source, UUID or semantic mismatch invalidates the comparison. |
| P1 | Unknown/unsupported health, concurrency and profiling data can be collapsed into a clean value. | Keep nullable/unsupported fields; unknown health or concurrent work blocks qualified comparison/reuse. Empty/malformed profiler or sanitizer artifacts are invalid. |
| P1 | CPU correctness is narrower than CUDA numerical qualification. | Keep unrounded FP64 oracle, exact input-family fixtures and frozen tolerance. Reject omitted scale, wrong epsilon, missing tail, input mutation and post-warmup output changes. |
| P1 | A manifest can record an operator declaration without enforcing it. | Tag evidence origin explicitly. A declaration of dedicated hardware is useful configuration, not measured exclusivity, resource enforcement or trusted external attestation. |
| P2 | Reusing a single public input can conceal specialization/cache behavior; repeated final feedback destroys held-out status. | Multiple fixed edge families and seeded inputs; fresh GPU copies and post-timing cases. Trusted probe fixtures remain development cases. Future S2 final sets have explicit retirement rules. |
| P2 | Many repetitions of one kernel are not independent coding-task samples. | Keep repetitions nested under one shape/candidate/device session; report local comparison and noise, no coding-success rate or production throughput inference. |

**VI:** Ưu tiên P0 giữ cho hệ thống không nhầm “không biết” thành “đã kết thúc/đã an toàn”. P1 làm kết quả có thể kiểm tra lại. P2 ngăn một phép đo nhỏ bị diễn giải thành năng lực tổng quát của agent.

## 4. Exact numerical and resource trace

For `R=1,H=3`, `x=[1,2,2]`, `scale=[2,-3,0]`, the squared row is `[1,4,4]`, sum is `9`, mean-square is `3`, denominator is `sqrt(3.00001)`, and output is `[2,-6,0]/sqrt(3.00001)`. The CPU oracle receives exactly represented FP32 inputs and compares each GPU output after conversion back to CPU against `abs(error) <= 1e-5 + 1e-4*abs(reference)`. Epsilon placement is distinguished by a separate tiny-magnitude input; the normal-sized row alone is weak for that defect.

| Value | Shape / dtype / location | Logical bytes and flow |
|---|---|---|
| `x` | `[R,H]`, FP32, contiguous CPU then CUDA | `4RH`; caller snapshot → transfer → both trusted arms |
| `scale` | `[H]`, FP32, contiguous CPU then CUDA | `4H`; snapshot → transfer → elementwise multiply |
| `reference` | `[R,H]`, FP64, CPU | `8RH`; independent scalar arithmetic → comparison only |
| `output` | `[R,H]`, FP32, CUDA then CPU copy | `4RH`; fresh result → synchronized completion → independent comparison |

At the maximum existing shape `R=64,H=4096`, one `x` or output is `1,048,576` bytes, scale is `16,384` bytes and the CPU reference is `2,097,152` bytes. `x+scale+output` is `2,113,536` logical GPU bytes. Eager temporaries, allocator blocks, contexts and library workspaces add residency; this formula is **not** a maximum device-memory guarantee. Kernel duration omits transfer/allocation according to the frozen boundary; component duration can include output allocation and synchronization, but not CPU oracle generation or initial upload.

**VI:** Các con số này bắt đầu từ số phần tử nhân byte mỗi phần tử. Chúng giúp phát hiện báo cáo sai đơn vị và hiểu luồng dữ liệu. Không được lấy tổng tensor để tuyên bố process chỉ dùng đúng bấy nhiêu VRAM, vì runtime và allocator còn giữ bộ nhớ riêng.

## 5. Decision and remaining evidence

Prepare one real trusted CUDA entrypoint, a pure manifest validator/observation reducer and CPU/mock tests under the existing compute module. Keep GPU work disabled by default and expose only the authored RMSNorm arms. A real GPU run remains pending. The source-only milestone can demonstrate validation, deterministic fixtures, exact failure categorization, timing-order orchestration with a fake backend and timeout handling; it cannot demonstrate a CUDA numerical pass, GPU duration, exclusive allocation, hostile isolation or safe GPU retirement.

The generated module build/launch, fixed ABI, privileged supervisor admission/health, physical GPU retirement and RuntimeStore integration are prerequisites for completing NV-S1 and then NV-S2. NV-S3 profiler/knowledge intervention and NV-S4 reviewed data consume those real records later. They do not justify an extra platform now. Production serving still needs the existing coverage register's provider/account, deployment, adversarial containment, restore, concurrency, SLO and operational evidence; this GPU slice does not replace it.

**VI:** “Code sẵn sàng đem test GPU” là mục tiêu có thể hoàn thành trước khi có máy. “Đã qua GPU test”, “chạy code lạ an toàn” và “production-ready” là ba kết luận khác, cần ba nhóm bằng chứng tương ứng. Human mastery vẫn chờ lời giải thích và transfer thật của Huy.
