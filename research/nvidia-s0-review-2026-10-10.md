# NV-S0 independent numerical and evidence review

Reviewed **2026-10-10** by the Astra architecture/review agent, separately from the two Sol source/test authors. Scope: the frozen CPU RMSNorm contract, `compute/rmsnorm.py`, and `tests/test_rmsnorm.py`. This review changes no runtime or test source. The initial design freeze is recorded by the coordinating agent; the canonical contract is [NV-S0](../capstone/07-reference-implementation-spec.md#nv-s0-frozen-cpu-numerical-contract).

**Disposition: no unresolved implementation blocker in this bounded CPU slice after two independently reproduced defects were repaired.** This is numerical and advisory-evidence validation, not GPU, generated-code, agent-capability, task-acceptance or human-mastery evidence.

## Findings and repairs

### R1: nested strided tensors bypassed malformed-input handling — repaired

An exact `torch.Tensor` can be nested, CPU, FP32, strided and contiguous, with `ndim == 2`, while refusing ordinary shape access. A nested tensor made from rows of lengths two and one passed the original initial checks. All three public numerical APIs then raised a Torch `RuntimeError` on `x.shape`, rather than the specified unsupported-input `ValueError`. A malformed candidate output could likewise escape the promised `outcome=invalid` path.

The source now rejects `value.is_nested` before shape-dependent operations. The independent test author added nested input/scale/output cases. This preserves the explicit dense rectangular envelope without attempting to pad or reinterpret data.

### R2: unequal storage base pointers did not establish independent memory — repaired

Separate `torch.frombuffer` wrappers can describe overlapping bytes while reporting different storage base pointers. The reviewer reproduced this with a 36-byte buffer, `x[2,3]` starting at offset zero, and `output[2,3]` starting at offset 12. Both were initially zero. The old checker returned `pass`; changing `output[0,0]` then changed `x[1,0]`. Base-pointer equality missed the declared independent-storage violation.

The source now compares whole storage address intervals. It rejects overlapping external-buffer wrappers and retains rejection of disjoint element slices that share one storage allocation. New tests cover overlaps with both `x` and `scale`. This is an in-process storage rule, not an isolation claim about hostile processes or externally remapped physical memory.

## Numerical and identity assessment

- The oracle converts exact FP32 input values into Python floats, performs a separate `math.fsum`/`math.sqrt` row calculation, and returns float64. Eager execution uses FP32 tensor arithmetic. The checker compares against the unrounded oracle with the frozen elementwise rule.
- Tests cover the hand calculation, signed/nonunit/zero scale, zeros, width one, multiple rows, non-power-of-two widths, supported magnitude/dimension limits and fixed-seed random data. Representable FP32 values around the tolerance boundary distinguish correct comparison from premature oracle rounding.
- Deliberately omitted scale, omitted tail, incorrect reduction and epsilon outside the root fail. The epsilon control uses small values because ordinary-size inputs can hide that error within the tolerance. The teaching trace reports one passing eager result and four failing controls.
- Validation rejects unsupported type, device, layout, gradient requirements, shape, nonfinite data and input ranges. Exact Tensor type checks occur before subclass dispatch; a reviewer-created subclass that raises from `__torch_function__` was rejected without dispatch.
- Tensor records hash canonical metadata plus exact logical element bytes, with an explicit native byte-order label. Lazy negative views are resolved for byte extraction. Independent probes confirmed matching observations for a negative view and its materialized equivalent, and different input digests for positive versus negative zero.
- Result tensors use independent storage. Returned observations contain owned JSON data. Independent probes changed nested contract/input metadata in an earlier observation and confirmed that a later observation retained the original contract and identities.
- Malformed/nonfinite outputs produce explicit invalid observations with null numerical metrics. Nonfinite output bytes may still have a digest; that digest identifies bytes and does not convert invalid evidence into a pass. JSON serialization uses finite values.

## Evidence boundary

The module accepts supplied tensors, computes its own reference and reports local numerical outcomes. It does not load generated code, accept supplied executable identities, issue `NumericalReceipt` objects, write RuntimeStore state or grant task acceptance. The record explicitly states that executable provenance is unestablished. A copied or forged observation dictionary is not an authorization object.

No GPU execution, timing, speedup, application benefit, isolation, device retirement, held-out task result, training improvement or human mastery was measured. The existing attention CUDA benchmark is not a trusted execution boundary for arbitrary generated CUDA host code. Those requirements remain in NV-S1 and later contracts.

**VI:** Review đã tìm hai lỗi thật: nested tensor làm sai loại kết quả lỗi, và hai storage khác địa chỉ đầu vẫn có thể chồng bytes. Sau sửa, S0 kiểm phương trình và nhận diện tensor đúng trong phạm vi CPU đã frozen. Một observation pass vẫn chưa chứng minh binary nào chạy, chưa cấp quyền acceptance, và chưa đo GPU.

## Verification performed by the reviewer

- Read the frozen contract and complete source/test files.
- Independently reproduced R1/R2 before repair; inspected the repairs and their new regression tests.
- Executed separate probes for lazy negative input/output, signed-zero hashing, metadata mutation, subclass rejection, gradient-bearing output rejection and teaching-trace verdicts. All those probes passed.
- Ran only `tests/test_rmsnorm.py`: **14 passed, 141 subtests passed in 1.24 seconds**. That run used test-file hash `0327adcf36c9b7badf8d7c414d57d9ca9a1cd62e80def4a7ff21556c3ced7c37`. The coordinator subsequently applied formatting only; the reviewer re-inspected the final regression cases and unchanged repaired source. No complete existing suite or GPU test was run by this reviewer.

Reviewed post-repair SHA-256 identities:

| File | SHA-256 |
|---|---|
| `compute/rmsnorm.py` | `b4d189671e30be3c6c0bbd3cff6668cd9d0dcae94fcb92651618feea9402a42d` |
| `tests/test_rmsnorm.py` | `c44f30b0fa68e99149a5eb87e1932bdc307e356099c6d1aa13c9dce59b04c79e` |

These hashes identify the inspected files; the coordinator's final verification record owns any later source changes and broader selected checks.
