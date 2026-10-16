# Trusted RMSNorm GPU qualification probe

Prepared **2026-10-11** under the [GPU boundary](../../research/gpu-boundary-spec-2026-10-11.md) and [closed configuration](../../research/gpu-probe-config-addendum-2026-10-11.md). Follow the [readiness plan](../../research/system-readiness-plan-2026-10-11.md) for final source/test acceptance. This probe runs only two authored FP32 RMSNorm implementations: eager arithmetic and PyTorch's library operation. It accepts no generated source, binary, plugin or arbitrary callable.

## Plan without execution

Save a private operator-selected configuration, replacing the illustrative UUID with the actual physical GPU UUID when hardware is available:

```json
{
  "schema": "nv-s1-trusted-rmsnorm-probe-v1",
  "mode": "trusted_authored",
  "paid_execution": false,
  "device": {
    "uuid": "GPU-00000000-0000-0000-0000-000000000000",
    "partition": "whole_gpu",
    "sharing": "exclusive_operator_declared",
    "reservation": "whole_device_capacity"
  },
  "host": {"deadline_seconds": 120, "max_output_bytes": 1048576},
  "seed": 20261011
}
```

```sh
python -m compute.rmsnorm_cuda --config /absolute/operator/gpu-probe.json
```

The default produces a byte-bound plan and `not_run` observation without importing CUDA or launching a child. Planning on this Mac does not validate the illustrative UUID or provision a GPU. On a separately authorized dedicated NVIDIA machine, the explicit `--run-trusted-probe` flag starts the fixed bounded child. It never rents hardware or enables a model provider. Keep rental and paid execution disabled in this workspace until the existing authorization changes.

**VI:** UUID trong ví dụ chỉ giúp đọc schema, không chứng minh có GPU. Một plan đúng là đầu vào cho thí nghiệm; không phải kết quả thí nghiệm.

## What the result can establish

The plan binds source identities, configuration, CPU fixture bytes, the FP64 correctness oracle and timing schedule. CUDA correctness precedes timing; output shape/dtype/storage aliasing/nonfinite values and input mutation are checked. The fixed schedule includes tail widths, alternating matched arms, A/A noise controls, warmups, CUDA-event durations, synchronized host intervals and allocator baselines/peaks. Outputs are released between samples. Raw observations remain inspectable.

An interrupted child, truncated output, device mismatch, failed synchronization or contradictory result cannot become a successful measurement. Missing driver/partition/concurrency evidence remains explicit; qualified performance ratios are withheld when qualification is incomplete. `measured_advisory` is a trusted-host observation, not a RuntimeStore receipt or device-retirement authority. Process-group exit does not prove GPU health or safe reuse after uncertain device work.

**VI:** Event CUDA đo device work sau synchronization. Host clock quanh enqueue không thay thế nó. Memory allocated/reserved cũng khác nhau; không lấy peak trừ baseline rồi gọi phần còn lại là toàn bộ VRAM cần dùng.

## Remaining real hardware and production gates

This machine has no CUDA. Actual GPU correctness, timings, driver/kernel compatibility, dedicated-device observation, contamination/noise and recovery require hardware evidence. The full NV-S1 generated-candidate path remains a separate boundary: isolated build/execution, protected verifier, durable GPU reservation, unknown-device quarantine and explicit retirement. This trusted probe cannot execute an agent's arbitrary kernel and does not establish its containment. NV-S2–NV-S4 optimization, profiler retrieval and reviewed data-lineage experiments also remain separate.

Preserve every hardware run under a fresh output directory with source/config/version identities and its full assigned workload. Do not merge CPU/mock numbers into a GPU speedup claim. Human H12 mastery remains independent from AI-authored implementation evidence.
