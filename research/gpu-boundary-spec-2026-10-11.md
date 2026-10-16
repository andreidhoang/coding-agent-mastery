# NV-S1 bounded GPU readiness specification — 2026-10-11

Status: **FROZEN before implementation, not implementation evidence**. Root selected `compute/gpu_contract.py` and `compute/rmsnorm_cuda.py`, the five functions in section3, and the default timing counts/shapes in sections4–6. CLI is `python -m compute.rmsnorm_cuda --config PATH` with optional `--run-trusted-probe`. Any omitted gate must be reported. This specializes [NV-S1](../capstone/07-reference-implementation-spec.md#ordered-implementation-slices), using the [primary-source audit](gpu-readiness-audit-2026-10-11.md). It creates no new benchmark population, evaluator, RuntimeStore schema or billing system. Paid execution is disabled throughout.

## 1. Selected output and scope

Build a real **trusted RMSNorm CUDA probe** that can be exercised later on one dedicated, already provisioned NVIDIA GPU, and build pure data contracts for its inputs/results. Its only executable arms are repository-authored eager FP32 RMSNorm and PyTorch `torch.nn.functional.rms_norm(..., normalized_shape=(H,), weight=scale, eps=1e-5)`. No user path, Python callable, generated source, plugin, command, shared library or cubin may enter this executable probe. The independent CPU oracle remains the existing NV-S0 implementation.

The probe is a local research tool producing advisory observations. It does not emit `NumericalReceipt`, `PerformanceReceipt`, task acceptance, a billing settlement or a physical-retirement claim. Generated-candidate execution remains unavailable in this implementation. Section 9 freezes its intended boundary so that preparation is useful without silently reusing trusted-probe privileges.

**VI:** Chương trình này trả lời: “GPU và phần mềm đã chọn có thực hiện đúng RMSNorm, và hai cách tính do ta sở hữu mất bao lâu trong điều kiện đã ghi?” Nó chưa trả lời: “Agent có thể viết và chạy CUDA tùy ý một cách an toàn không?”

## 2. Owners and invariants

| Owner | State/data owned | Invariant |
|---|---|---|
| `compute/rmsnorm.py` | Equation, CPU validation and reference/observation versions | Existing FP32 envelope, FP64 oracle and tolerance remain unchanged. |
| New compute GPU module(s) | Frozen probe policy, bounded fixture construction, authored arms, timing sequence, observation validation | Never execute external candidate code; never substitute CPU/MPS for unavailable CUDA; never report mocks as measurements. |
| Trusted parent supervisor | Child process identity, start/exit/output limits and final result interpretation | A successful JSON body requires complete normal child exit and process-group retirement; child output alone cannot prove either. |
| Child probe | CUDA device selection, tensors, synchronization and raw samples | One selected device/stream; correctness gates timing; every measured output is released before the next call; asynchronous errors remain failures. |
| Operator/environment | Dedicated physical allocation and permitted local resource envelope | A manifest declaration records intent; it is not enforcement or an attestation. No automatic rental, networking, reset, privilege escalation or clock mutation. |
| Existing artifact helpers | Canonical immutable JSON/byte digests | Exact source/config/input/output identities, finite JSON and detached returned values. |
| Existing RuntimeStore | Any later task authority/reservations | The probe never changes RuntimeStore. A future adapter must preserve current-owner fencing, unknown effects and occupied physical slots. |

Every API rejects unknown schema versions/fields, nonboolean Boolean values, Boolean integers, nonfinite numbers, invalid ranges and aliased mutable return values. Unsupported hardware or missing metadata is explicit, never a zero measurement. Design choices below are project policy, not empirical performance facts.

**VI:** Metadata đúng format chỉ chứng minh parser hiểu dữ liệu. Nó không chứng minh người cung cấp metadata thật sự cô lập GPU. Vì vậy cần giữ trường “declared/observed/mock” và không cho parser tự cấp authority.

## 3. Suggested public surface and execution gate

Suggested filenames are `compute/gpu_contract.py`, `compute/rmsnorm_cuda.py` and focused tests. The integration owner may consolidate them without changing behavior. Public functions should provide: `probe_contract()`, `validate_probe_config(config)`, `build_probe_plan(config)`, `validate_probe_observation(plan, observation)` and `run_trusted_probe(config, *, execute=False)`. A CLI exposes the same fixed path; exact names are recorded at freeze.

Default execution produces `not_run` plus the bounded plan and required hardware evidence. It must not initialize CUDA, launch a child, invoke a compiler, query a remote API, download a model/image/package or mutate GPU state. A separate explicit `--run-trusted-probe` option enables a fresh bounded child on an already provisioned local worker. No GPU run is performed in the October11 CPU preparation session. CUDA unavailability returns `unavailable` with `fallback:null`, absent/null performance values and no “pass.”

The parent uses the existing bounded process mechanism with an argument vector and explicit executable/module; no shell interpolation or caller-provided command. Source/config identity is captured before launch and checked against the child result. Result parsing is bounded, rejects duplicate keys/NaN/trailing garbage and requires the complete expected schema. A source digest is a provenance check for this trusted checkout, not cryptographic attestation of the OS, imported library binary or driver.

**VI:** Cờ chạy là sự phân biệt thao tác “chuẩn bị” với “thực thi”. Nó không tự thuê máy hay cho phép tiêu tiền. Child process tách vòng đời GPU probe khỏi controller; nếu child treo, parent vẫn có thể ghi trạng thái không xác định.

## 4. Manifest and resource contract

The manifest is strict finite JSON, bounded to 64 KiB. Recommended schema identifier is `nv-s1-trusted-rmsnorm-probe-v1`. Exact source-file byte hashes, contract digest, fixture-generator version and Python/PyTorch versions are required in the resulting observation. Device fields are observed at execution and checked against the requested identity.

| Field/group | Required meaning and bound |
|---|---|
| `mode` / paid policy | Literal trusted-authored probe; `paid_execution:false`; generated execution rejected. No caller-supplied command/source/module fields. |
| Device allocation | Exactly one physical GPU UUID (not a mutable ordinal alone), `partition:whole_gpu`, `sharing:exclusive_operator_declared`; MPS and MIG excluded in v1. Record any externally enforced reservation separately. |
| Environment identity | Observed GPU UUID/name/compute capability/total device bytes, driver and CUDA-runtime versions; Python/PyTorch version, source hashes, lock identity where available. Missing fields cannot qualify a matched comparison. |
| Host envelope | Parent deadline default 120 s, allowed 1–600 s; combined output cap default/max 1 MiB; no external process/command parameters. These are process bounds, not OS CPU/RAM/PID enforcement. Any declared container limits retain their enforcement source. |
| GPU memory | `reservation:whole_device_capacity`, observed capacity in bytes. Logical tensors and PyTorch allocated/reserved/peak counters are distinct. No asserted sub-device hard quota. Reject `hard_vram_limit_bytes` claims for this profile. |
| Work | Existing `1<=R<=64`, `1<=H<=4096`; fixed shape list and bounded CPU seed; FP32 inference; exact epsilon/tolerance from S0; no half/bfloat/backward/autocast/compile variants. |
| Timing policy | Warmup 10 per arm; 30 matched AB/BA repetitions per timed shape; 10 A/A pairs using the same eager implementation; one call per sample; no adaptive stopping or best-of filtering. Counts may be narrowed at freeze, but are immutable within one plan. |
| Privileges/network | Probe itself uses no network, compiler, profiling privilege or control socket. No reset/power/clock/MIG-management commands. Inherited environment must not add executable plugins/preload hooks; the future dedicated-worker image owns broader isolation. |
| Observation origin | `real_cuda`, `mock` or `not_run`; mocks cannot produce a real-measurement verdict; operator declarations remain labeled. |

The runnable trusted probe may accept an operator-declared dedicated device to produce **advisory** observations. It must not claim to enforce exclusivity merely from a pre-run `nvidia-smi` process list. Pre/post foreign-process checks can reject known contention; they cannot prove absence throughout the interval. If the first implementation lacks reliable observed UUID/driver/partition/concurrency data, preserve the missing values and withhold qualified comparison rather than synthesizing identities.

**VI:** 120 giây là giới hạn parent chờ và xử lý child. Nó không phải lời hứa kernel chắc chắn ngừng trong 120 giây. Tương tự, “whole GPU” là phạm vi tài nguyên dành riêng; không có cgroup RAM nào biến thành quota VRAM cho CUDA tùy ý.

## 5. Numerical fixtures and exact data flow

Reuse the frozen S0 equation and compare copied FP32 results to the unrounded CPU float64 oracle. Fixture construction is CPU-only, deterministic, bounded and independent of either CUDA arm. Include `[1,2,2]` with nonunit/negative/zero scales, all-zero rows, width1, tiny magnitudes distinguishing epsilon location, widths3/31/33/257, and a seeded maximum-shape case `64x4096` with both inclusive magnitude limits. Suggested timing shapes are `(1,33)` and `(64,4096)`; all correctness fixtures remain in the same probe plan.

Flow: immutable CPU FP32 fixture → exact input digest and CPU reference → CUDA copy → authored arm → successful synchronization → fresh CPU output copy → `check_rmsnorm` → unchanged-input comparison. Both arms must pass every pre-timing case. Compare original CUDA input/scale copies after each arm; the CPU originals remaining unchanged does not prove GPU inputs were not mutated. Recheck the timed outputs and changed-input cases after timing. A wrong result at any point invalidates performance comparison.

The eager arm uses FP32 square/row mean/square root/scaling. The PyTorch library's internal accumulation/dispatch is recorded as backend dependent unless independently inspected for the selected device/build. Both return fresh dense contiguous FP32 outputs with matching shape and no input alias. Use inference mode; explicit device selection; no autocast; no implicit dtype conversion to make a failing output pass. Unsupported library support is a visible unsupported arm, not a silent eager replacement.

**VI:** Nếu output cuối đúng nhưng warmup từng đổi input, hai arm có thể đã đo hai bài toán khác nhau. Vì thế cần giữ CPU snapshot và kiểm tra bytes trên GPU sau khi chạy. Sai số chấp nhận giữ nguyên; không nới tolerance sau khi nhìn kết quả để tạo pass.

## 6. Timing, units and statistics

All inputs are allocated/transferred and CPU references computed before timing. For each shape, warm both arms exactly as planned and release each warmup result before the next call. Synchronize the selected device after warmup. Allocation policy is warm PyTorch cache, no `empty_cache` between samples/arms; no output may remain live across the next right-hand-side evaluation. Record that policy and each arm's allocator baselines; it is not cold-start capacity.

For each sample, pre-create timing events; synchronize before the host start; record the start event on the selected stream; call one authored arm; record the stop event; synchronize completion; stop `perf_counter_ns`. Read event time only after successful completion. `device_elapsed_ms` describes the event interval around the full arm's queued CUDA work, potentially multiple kernels. `component_elapsed_ns` includes the Python dispatch, output allocation, GPU execution, synchronization and measurement instrumentation inside that host interval. It excludes process startup, input upload, CPU oracle and output download/checking. Neither metric is automatically a selected single-kernel duration or end-to-end service latency.

Capture allocator peaks before correctness/error scratch allocations. Keep starting/peak allocated and reserved bytes and their nonnegative deltas using the existing accounting helper. Peak reserved cache is not total process/device VRAM. Record optional device memory observations separately with their sampling scope. Transfer/setup time may be separately reported, with explicit units, but cannot be inserted into one arm's core timing only.

**VI:** Hai đồng hồ nhìn hai đường biên khác nhau. Event nói GPU đi qua vùng đã đánh dấu bao lâu; host timer nói một lần gọi cộng chi phí chờ mất bao lâu. Nếu kernel nhỏ, overhead có thể lớn hơn thời gian GPU, nên không được đổi tên host timer thành kernel latency.

AB/BA order alternates by repetition, retaining shape, arm, pair index and order in every raw sample. A/A uses the same eager function under two labels, with the same policy and data. Each sample must be finite and strictly positive; integer host nanoseconds must be nonboolean. No discarded “bad” samples, silent rerun or zero-time speedup. Preserve failed/incomplete samples as explicit outcomes.

Report count, median and bounded spread for raw device and host distributions. An optional observational ratio is `median(eager)/median(pytorch_rms_norm)` for the same device/config/shape/session; label the numerator and denominator. A/A median ratio and spread are diagnostics. If a noise threshold is used, freeze it (suggested development policy: A/A ratio within `[0.90,1.10]`) and label failure `unstable_measurement`; the threshold is not a statistical significance claim. Ratio is null on wrong output, incomplete samples, unknown units, identity mismatch, known contention or unstable calibration. No aggregate “speedup” across unrelated shapes, no production-serving gain and no performance acceptance receipt.

Profiler/sanitizer execution is outside clean timing. Later diagnostic records bind tool/version/flags/kernel scope and coverage to the same source/binary/config. Missing reports/coverage are invalid. Profiling cannot be enabled through a generic caller command or privileged fallback in this probe.

**VI:** A/A cố tình đo cùng phép tính hai lần để xem hệ đo tự tạo ra “cải thiện” bao nhiêu. Nếu A/A đã lệch lớn, A/B chưa đáng tin. Nhiều sample trong một session giúp hiểu nhiễu của session đó; chúng không biến thành nhiều task độc lập.

## 7. Result, exit and uncertainty contract

Top-level states are `not_run`, `unavailable`, `rejected`, `failed`, `measured_advisory` and `unknown`. These are observations, not task terminal states. Keep `fallback:null`, `performance_acceptance:false`, `generated_execution:false` and `paid_execution:false` explicit. The validator recomputes summaries/digests from bounded raw values; it does not trust a child summary or a caller's `passed:true`.

| Condition | Required outcome |
|---|---|
| Default invocation | `not_run`; zero external execution; no fabricated physical measurements. |
| CUDA absent before work | `unavailable`; no fallback; no timing/ratio. |
| Invalid manifest, source, device, schema or units | `rejected`; do not begin dependent execution. |
| Known synchronous exception, numerical failure or unsupported arm | `failed` with stage/reason and existing bounded evidence; no ratio. |
| Complete source-bound report + normal zero exit + full output + process-group retirement + all numerical/sample gates | `measured_advisory`; measured trusted-code scope only; no isolation/physical-slot claim. |
| Timeout, signal, truncated/malformed/missing child result, process-group retirement missing, CUDA fault or synchronization uncertainty | `unknown` when device work may have started; preserve possible activity and prevent automatic relaunch/reuse. |

Track separately: whether a GPU operation may have started; child-reported successful synchronization of all its work; parent-observed process-group retirement; external device retirement; health and reservation reuse. The last two remain `unverified` in the trusted local probe unless a separate trusted supervisor observes them. A normal child completion demonstrates only the declared probe scope. `cuda.empty_cache`, event destruction, PID absence, zero utilization or container removal cannot independently prove faulted work has retired. Do not reset a device automatically.

For a future RuntimeStore adapter, unknown effect/charge and unknown physical retirement remain independent. A locally free probe has no provider-billing record; report billing as not applicable/unmetered rather than fabricate a zero-cost receipt. Any later paid execution needs a separately authorized envelope; this contract cannot enable it.

**VI:** Có thể biết process chết nhưng chưa biết GPU đã sạch để tái sử dụng. Cũng có thể biết GPU xong nhưng chưa biết hóa đơn cuối. Giữ các trạng thái riêng giúp hệ thống không xóa nghĩa vụ chỉ vì một hàng trạng thái đổi sang “done”.

## 8. CPU/mock acceptance and distinguishing controls

Tests must not require CUDA, mutate global authority, call paid services or rent hardware. The independent oracle tests use their own scalar calculation/tiny expected values, not the implementation's helper as both producer and judge. A narrow fake backend can test operation ordering; mock timing remains tagged `mock` and cannot yield a real GPU claim.

1. **G1 disabled execution:** monkeypatch CUDA initialization, subprocess, compiler and network entrypoints to fail if default/offline mode touches them. Explicit missing-CUDA case returns unavailable and no samples.
2. **G2 manifest strictness:** unknown fields/version; Boolean counts; negative/zero/oversized bounds; NaN/Infinity; multiple devices; mutable ordinal-only identity; MIG/MPS; arbitrary code/command; false hard-VRAM enforcement; paid=true; changed source digest are rejected.
3. **G3 independent arithmetic:** hand oracle and known good output pass; omitted scale, tail/reduction/epsilon defects, wrong dtype/layout/nonfinite/alias/input mutation fail without tolerance changes. Changed CUDA input simulation must be rejected even when CPU originals are unchanged.
4. **G4 timing sequence:** fake operation ledger requires warmup before samples, start before call before stop, synchronization before elapsed reads, every output release before next call and all correctness cases before timing. Reject enqueue-only timing and after-timing wrong output.
5. **G5 sample semantics:** nonfinite/nonpositive values, ns/ms mismatch, wrong sample count/pair ordering, negative allocator deltas and mismatched arm/device/config/source are rejected. Independently compute tiny-list medians and ratios; summaries must be recomputed. A/A failure removes ratio.
6. **G6 completion:** a plausible success body plus timeout/nonzero exit/truncation/unretired process must not become measured. Unknown after possible device start prevents automatic retry. No container/PID signal alone produces device retirement.
7. **G7 provenance:** changing fixture, source, policy, version, UUID or artifact bytes changes/rejects the correct identity; mutating caller/returned dictionaries cannot alter stored contract/observation. Duplicate JSON keys and trailing bytes fail.
8. **G8 hardware opt-in:** GPU test is explicit and reports skip/unavailable without hardware; its CPU skip is not a GPU pass. A later real session must retain raw version/source/profile/input/output/sample/lifetime evidence.

Required independent review targets G3–G7 and the trust split. Tests should inject plausible defects into disposable copies: remove synchronization, accept child stdout after timeout, and treat allocator fraction/container death as device isolation/retirement. Preserve reference source and previous evidence. Run appropriate affected regressions once; documentation edits do not justify repeated full suites.

**VI:** Fake backend chỉ chứng minh thứ tự gọi do controller yêu cầu. Nó không biết CUDA driver có thật sự làm đúng hay không. GPU test thật sẽ lấp phần đó; test CPU vẫn có giá trị vì bắt được sai contract và logic trước khi dùng tài nguyên thật.

## 9. Frozen future generated-candidate boundary

Completing generated-code NV-S1 requires one disposable dedicated Linux worker/VM with one exclusive physical GPU assigned to the session; CPU/RAM/PID/scratch/time limits enforced by the worker supervisor; no credentials, model API keys, host mounts, control sockets, network egress, MPS or sharing. The full GPU memory capacity is the admitted resource envelope. A separate future MIG profile requires a specific hardware/driver/instance isolation review; it is not enabled through a string change.

Build is a separate no-GPU environment with an immutable compiler image, fixed headers/flags/entry symbol and bounded `.cu` bytes. It produces a device-only cubin for a fixed SM target; compiler output is evidence. A trusted launcher uses the CUDA Driver API and a fixed RMSNorm ABI, supplies buffers/shape/grid/stream, owns events and copies outputs to a separate CPU verifier. No candidate host binary, Python extension, shared library, C++ initializer or dynamic loader is run in the measurement authority. No device-side dynamic parallelism/runtime linkage in the first ABI. Candidate source, compile inputs, cubin bytes and launcher image/version bind one receipt chain. Driver/compiler parsing remains a risk bounded by the dedicated worker, not a proven absence of vulnerabilities.

The launch supervisor writes physical intent before dispatch and binds worker identity, GPU UUID, reservation, immutable instance/creation nonce and task/attempt/dispatch when integrated. On fault/timeout it quarantines the worker, retains reservation/exposure and requires externally observed process/context retirement plus supported GPU recovery/health checks before reuse. Recovery mechanisms may require replacing/power cycling the worker; the agent may not escalate to reset or host privilege. Merely receiving a zero exit or empty process list does not implement this contract.

**VI:** Chỉ đưa “chương trình chạy trên GPU” vào boundary đo, còn chương trình host gọi nó phải do hệ thống sở hữu. Sau lỗi, supervisor cần chứng cứ thu hồi ở mức thiết bị/worker. Đó là phần khác hẳn với kill một lệnh Docker.

Before generated execution is enabled, separately freeze and implement: concrete worker reservation/enforcement; compiler/device ABI and static/build controls; trusted launch/output/measurement channel; sanitizer coverage; journal/recovery/health adapters; RuntimeStore owner/accounting integration; and real hardware fault/retirement tests. Then NV-S2 may connect one agent-produced candidate to this same workbench. NV-S3 and NV-S4 consume actual records afterward. Existing public benchmark tasks remain development references, and the original evaluator population stays unchanged.

## 10. Acceptance wording and handoff

Source delivery may say: **“Trusted RMSNorm CUDA probe and CPU/mock contract tests implemented; real CUDA validation pending; generated-candidate execution disabled.”** It may not say “NV-S1 isolated GPU runner complete,” “GPU benchmark passed,” “hard VRAM capped,” “safe GPU retirement,” “production serving ready” or “human mastery demonstrated” without their separate evidence.

Record source hashes, actual API/CLI names, executed tests/skips, independent review, remaining hardware inputs and any deviations from this proposed policy in the implementation's own verification record. Freeze this selected contract before implementation; use additive amendments for later findings. The current research slice changed only this document and the associated audit. No GPU, provider, runtime, evaluator or paid-resource action was performed by the audit.

**VI:** Handoff cần đủ để người sau biết đã chứng minh gì và còn thiếu gì. Tên file không hoàn thành milestone; test mock không trở thành số đo GPU. Những gì đã có vẫn mở đường cho lần test thật mà không cần viết lại toàn bộ contract.
