# Independent GPU probe review — 2026-10-11

**Updated decision: both P2 defects below are repaired. The integration owner reran all12 unchanged independent controls successfully against corrected source; CPU/mock acceptance only.** The trusted numerical/transport core passed the listed CPU/mock controls. This review performed no CUDA execution, provider request, GPU rental or paid operation. It did not edit implementation or repository test files.

The authority is the [frozen probe contract](gpu-boundary-spec-2026-10-11.md) and [configuration addendum](gpu-probe-config-addendum-2026-10-11.md). The reviewer inspected both new modules, their tests and the existing bounded-process implementation. Source preparation is distinct from GPU qualification, generated-code isolation and production serving. The original reviewer findings and hashes below remain historical evidence; the final correction record is linked at the end.

**VI:** Hai lỗi validation được sửa và coordinator chạy lại control độc lập thành công. Evidence vẫn chỉ là CPU/mock, không thay thế test CUDA hay chứng minh thiết bị đã được thu hồi.

## Findings reproduced before repair

### R1 — P2: use byte-exact plan identity rather than Python value equality

[Plan validation](../compute/gpu_contract.py#L185) compares nested dictionaries with Python equality; [the child precheck](../compute/rmsnorm_cuda.py#L249) uses the same pattern. Changing `contract.cpu_threads` from integer `1` to Boolean `true`, or `warmup_per_arm` from integer `10` to float `10.0`, is accepted by the public validator while retaining the original `plan_digest`. Python considers those values equal despite different canonical JSON and the strict integer/type contract.

The independent `exact_plan_identity` control reproduces both cases. This does not grant task authority, but it breaks the advertised immutable source/config/policy identity and permits a plan that was not hashed as presented. Compare canonical bytes to a rebuilt plan, or strictly validate and recompute the body digest, in both parent/reducer and child entry paths. Add regressions for Boolean/integer, float/integer and altered nested fixture/contract representations with unchanged saved digests.

**VI:** `True == 1` đúng trong Python nhưng không có nghĩa hai manifest là cùng bytes. Khi digest mô tả bytes, phép so sánh cũng phải giữ đúng kiểu và cách biểu diễn của contract.

### R2 — P2: reject contradictory complete results and incomplete numerical metrics

[Failed-sample validation](../compute/gpu_contract.py#L331) accepts `schedule:null` when all planned samples exist. [Complete-result validation](../compute/gpu_contract.py#L348) does not require `failed_sample:null`. Consequently a fabricated complete report carrying `{schedule:null,stage:"timing_completion",reason:"CUDA synchronization failed"}` is accepted as `measured_advisory` and receives matched advisory ratios. The independent `contradictory_complete_failed_sample` control records that contradiction.

The related [numerical metric check](../compute/gpu_contract.py#L295) allows `max_absolute_error:null` even when a numerical check claims `outcome:pass`; `null_success_metric` reproduces promotion to `measured_advisory`. Require no failed-sample record in a complete result and non-null finite nonnegative error metrics for `pass`/`fail` numerical observations; retain explicitly invalid-output semantics separately. Reject inconsistent lifecycle/status records instead of deriving a comparison from them. These are reducer validation defects; no actual CUDA failure or compromised child is claimed.

**VI:** Một record vừa nói “đã đo đầy đủ” vừa nói “synchronize thất bại” không thể có ratio đáng tin. Tương tự, `pass` cần metric số học thật của check; null là thiếu evidence, không phải sai số bằng 0.

## Executed evidence

Evidence directory: [gpu-review — local-only](../docs/github-snapshot.md#omitted-local-evidence). The [independent controls — local-only](../docs/github-snapshot.md#omitted-local-evidence) do not import the author's test helpers. [Initial controls — local-only](../docs/github-snapshot.md#omitted-local-evidence) preserve the first reproductions; [expanded controls — local-only](../docs/github-snapshot.md#omitted-local-evidence) add the independent timing/output-lifetime check. Fabricated reports are explicitly labeled test data in the artifacts.

| Control | Observed result |
|---|---|
| Existing focused tests | `83 passed, 141 subtests passed in 5.86s` for `tests/test_gpu_probe.py tests/test_rmsnorm.py`; no skips. This overlaps author evidence. |
| Default invocation with process/network/child traps | Returned `not_run` without invoking forbidden paths. |
| Actual CPU child emits complete fabricated JSON, then exits7 | Parent returned Unknown; no ratio; process group retired. Child imported no project or CUDA code. |
| Actual CPU child emits complete fabricated JSON, then waits beyond deadline | Observed timeout and signal termination; parent returned Unknown despite complete-looking body and retired process group. No device-retirement inference. |
| Altered source/lock/device identity | Each rejected. |
| Driver, partition, concurrency or MPS evidence missing | Ratios withheld independently for each field. |
| Independent CPU scalar oracle | Both authored arms passed all10 planned fixture cases:20 CPU comparisons, including changed values and maximum shape. Oracle uses its own `math.fsum` and square-root derivation. No CUDA numerical pass inferred. |
| Independent fake timing state machine |160 fabricated samples across240 calls; start/call/stop/completion order enforced; weak references confirm previous output object is gone before the next call; mock results cannot become real measurements. |
| Exact nested plan types | R1 reproduced for integer→Boolean and integer→float. |
| Contradictory completion / null passing metric | R2 reproduced; this is an expected negative finding, not a passing acceptance control. |

**VI:** Hai child process thật ở đây chỉ ghi JSON giả rồi exit hoặc sleep; chúng kiểm tra supervisor của host, không tạo CUDA context. Phần weak-reference kiểm tra object output thực sự được thả, mạnh hơn chỉ tin một cờ `released:true` do fake backend tự đặt.

## Inspected CUDA branch and retained limitations

The executable path fixes its own Python module and authored arms, clears caller environment through a fixed argument-vector launcher, rejects loader hooks, selects a single requested physical UUID and accepts no candidate code path. The actual CUDA branch prepares CPU references, uploads fixtures, uses an explicit CUDA stream, checks copied results and GPU input bytes, records event and synchronized-host intervals, releases outputs and captures allocator peaks before error scratch. Parent completion checks normal exit, output completeness and process-group retirement independently of the body.

The installed hardware branch has not been executed. Its UUID-property behavior, CUDA library dispatch, event timing, asynchronous error propagation and output/allocator behavior remain hardware tests. Driver metadata may be absent; partition, MPS and contention evidence are deliberately unverified in the runnable branch, so qualified ratios remain null. Source/version hashes are trusted-checkout provenance, not OS/driver/library attestation. The probe does not enforce exclusive scheduling or a general VRAM quota; it cannot establish external GPU retirement, health or reservation reuse and performs no RuntimeStore transition. R1/R2 repairs cannot upgrade these claim limits.

**VI:** Code đã chuẩn bị có thể được kiểm tra theo cơ chế, nhưng GPU thật vẫn là bước xác nhận độc lập. Không có bằng chứng nào ở review này cho phép nói “hostile CUDA isolated”, “GPU safely retired” hoặc “production serving ready”.

## Reviewed identities and handoff

| File | SHA256 |
|---|---|
| `compute/gpu_contract.py` | `fe96b9319d2b5618ac10caff20aad94ab8797870d66693db679258a81e06eef4` |
| `compute/rmsnorm_cuda.py` | `7dd361f0d3c93e7174d0014008af5c9e896cb0f66c19a4298f3b953dcbd23b30` |
| `tests/test_gpu_probe.py` | `f1f71c0ab8f9e9e497d9ce27fae3052661c6a62f50c75fe59bfd9397ed78ced2` |
| Probe specification | `ff3e5a4e4c49eb85233fd63ee16852876f4869154a1e2f0d5803b34ed1c1705a` |
| Configuration addendum | `6e744b5b8add9fe713d55f97e8e07fe735938b48f549a4456e1959ab8158811b` |
| Preserved `uv.lock` | `9e80b9a78d1965e5691625661e72172a53d378dc09fa4ace230b105726b238b7` |

The bounded coder repaired R1/R2 and added13 regressions:96 tests and141 subtests passed, with no skips. [Author correction record — local-only](../docs/github-snapshot.md#omitted-local-evidence). The integration owner independently reran the unchanged control source, redirecting only its output directory to preserve original evidence: [final controls and corrected source hashes — local-only](../docs/github-snapshot.md#omitted-local-evidence). All12 controls completed; Boolean/float plan changes, contradictory completion and null successful metrics now reject. This paragraph is an integration-owner update; it does not claim the Astra reviewer ran the later gate. No GPU or production claim follows. Human mastery and paid-execution policy remain unchanged.
