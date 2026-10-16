# Independent GPU disposable-source mutation review

Date: 2026-10-11. Target: the three required disposable-source defects in [GPU boundary specification §8](gpu-boundary-spec-2026-10-11.md#8-cpumock-acceptance-and-distinguishing-controls). Product source, maintained tests and the accepted rc2 candidate were preserved.

**Result: the unchanged copy passed three positive controls; three separate defective copies were rejected by their corresponding independent oracles.** These are CPU/fake-data tests. No Torch import, CUDA/GPU execution, model request, network call, rental or container action occurred.

The runner extracts only the existing independently authored fabricated-report, actual fake-child timeout and operation-order/weak-reference control functions from `gpu-review/independent_controls.py`. It does not execute that script's root discovery, full suite or arithmetic/Torch case. A new independent false-authority oracle supplies the third case. Each isolated process imports only its selected disposable product copy, records all import origins and builds its plan against that copy's own source hashes. Thus mutation rejection is not an accidental stale-source digest rejection.

| Disposable defect | Exact change | Distinguishing rejection |
|---|---|---|
| Missing required completion synchronization | Delete the single `backend.sync()` between `timing_completion` and the host completion timestamp. | The fake operation ledger fails at `timing_completion: AssertionError`; no timing sample is completed. The unchanged copy completes160 mock samples and240 calls with released outputs. |
| Accept plausible stdout after timeout | Disable the parent's `if not complete` rejection branch, leaving the same bounded child transport and body validator. | A real CPU child writes fabricated complete JSON and then exceeds its0.25s bound. The defective parent promotes the timeout body to `measured_advisory` with nonempty ratios; the oracle requires Unknown/no ratio and rejects it. The unchanged parent reports Unknown after the same fake-child timeout. |
| Process death becomes device retirement | Weaken only the actual observation validator's external-retirement guard when `process_group_retired=True`. | The defective validator accepts `external_device_retirement=retired` from process-group termination alone. The oracle rejects that false authority; the unchanged validator raises its explicit no-physical-authority invariant. |

The third requested allocator-fraction/container-death policy is structurally absent from the compute probe: it sets no allocator fraction and owns no container-to-device retirement mechanism. The smallest applicable mutation therefore weakens the real validator's exact authority boundary. It leaves all other health/reuse fields and validation rules intact. The body is explicitly fabricated review data, not a genuine device observation.

Every mutation patch, original/mutated source hash, source copy, captured stdout/stderr, argv, observed failure and positive-control result is preserved under [mutation evidence — local-only](../docs/github-snapshot.md#omitted-local-evidence). Verification SHA-256: `1da3272917d9396aff27686cee2b4df831623dd33bd142249c07b2f231946da3`. The10 selected reference files and all325 regular files in rc2 were unchanged before/after these experiments. No broad suite was rerun.

**VI:** Mutant timeout vẫn có JSON “đẹp” và ratio hợp lý, nhưng parent không có bằng chứng child hoàn tất bình thường. Oracle bắt đúng sự khác biệt giữa nội dung và lifecycle. Mutant thứ ba cũng cho thấy PID đã chết không chứng minh GPU work đã retire; authority đó cần evidence riêng từ supervisor đáng tin. Các fake controls kiểm tra logic này trước khi dùng GPU, không thay thế hardware validation.
