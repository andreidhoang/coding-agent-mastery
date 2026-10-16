# Research, compute and workload audit — 2026-10-10

**Scope and result.** Read-only audit of every Python module in `compute/` and `evals/`; `workloads/registry.py`, `fixture.py`, `freeze_catalog.py`, all manifest/evidence JSON, and the corresponding six test modules (`test_compute`, `test_rmsnorm`, `test_evaluation`, `test_simulation`, `test_audit_research`, `test_workloads`). Also inspected the existing artifact/report/snapshot/event/verification interfaces for the proposed adapter. Read AGENTS, current state, H0 reference packet, role contract06, implementation specification07 and coverage08. Archived sources and vendor/course snapshots were not re-audited. Frozen baseline/oracle variants were integrity-checked as assets, not represented as independently reviewed runtime modules. Audit author: AI; no human mastery or independent human reproduction inferred.

The current division of ownership should remain. The measured CPU reference is appropriately separated from execution/acceptance, the evaluator owns assigned denominators, and the registry preserves synthetic family provenance. Three bounded input defects were reproduced below. Repair these before adding a new subsystem. The existing failure-evidence/regression adapter is the next justified shared foundation, but its implementation should follow an explicit frozen contract and independent review. This audit did not write production source/tests, execute candidate code, run paid inference or start a GPU.

**VI:** Audit này kiểm source và thử input phân biệt lỗi trong thư mục tạm. CPU tensor pass không phải execution receipt; 42 workload vẫn thuộc một family tổng hợp. Ưu tiên sửa lỗi thực sự trước, rồi mới nối evidence vào regression bằng contract rõ ràng.

## Reproduced findings

### R1 — P2: acceptance counts a missing candidate identity

At [analysis.py:56 — local-only](../docs/github-snapshot.md#omitted-local-evidence), required fields are checked only for absence/`None`; at [analysis.py:74 — local-only](../docs/github-snapshot.md#omitted-local-evidence), candidate identity is checked only by equality. Thus `candidate_digest=verified_digest=""` or both `{}` scores accepted. This contradicts the analyzer's exact-candidate identity contract even within its explicitly trusted-input boundary. It does not demonstrate a RuntimeStore acceptance bypass.

Reproduced with `.venv/bin/python`, one-task/two-arm `demo_manifest`, its first planned row and `accepted_fixture`:

```python
for value in ("", {}):
    result = accepted_fixture(row, candidate_digest=value, verified_digest=value)
    assert analyze(frozen, [result], bootstrap=1)["counts"]["accepted"] == 1
```

Small fix: require nonempty string identities for the acceptance fields, including candidate/verified digest and receipt references, before equality checks. Preserve clearly labeled synthetic string identities; imposing SHA256 on the arithmetic fixtures would unnecessarily replace their established contract. Malformed claimed acceptance should score zero with the existing `accepted_claim_without_eligibility` reason, or be explicitly rejected by a documented validation policy. Distinguishing tests: equal empty/non-string identities rejected, genuine matching identity accepted, changed identity rejected; assigned denominator and accounting unchanged.

### R2 — P2: cumulative snapshots can contain facts from their own future

[analysis.py:99 — local-only](../docs/github-snapshot.md#omitted-local-evidence) validates `recorded_at`; lines102–111 validate event times independently. No event time must precede the snapshot's recording time. `accepted_fixture(row, recorded_at=1)` contains verification30, eligibility31/32 and review40, yet scores accepted1. This is an internally impossible cumulative snapshot under the README's single-time-coordinate contract. The acceptance predicate separately checks analysis/review cutoffs, so this reproducer is chronology-integrity failure, not proof that the existing cutoff check itself accepts reviews after cutoff.

Small fix: reject any supplied observed event time greater than `recorded_at`; do not silently backdate it. Apply to submitted, verified, eligibility decision/commit, review and withdrawal facts when present. Keep equality legal and keep an otherwise valid later revision from changing the earlier cutoff result. Distinguishing test: same accepted row recorded120 passes, recorded1 rejects; each timestamp field gets a future-fact control; cumulative spend and prior revision retention remain covered by existing regressions.

### R3 — P2: static candidate admission silently ignores nonregular entries

[registry.py:193 — local-only](../docs/github-snapshot.md#omitted-local-evidence) handles symlinks, directories and regular files but has no final rejection branch. A FIFO named `undeclared_fifo` alongside a valid materialized task returns `pending_linux_verification` with `problems=[]`. This violates the claimed undeclared-path/type boundary and omits the entry from the candidate tree identity. This is a local inspector flaw; no hostile execution or downstream verifier bypass was demonstrated.

Reproducer used only `TemporaryDirectory`, `materialize_task("calibration-01", ...)`, `os.mkfifo(root / "undeclared_fifo")`, and `inspect_candidate`; it did not open/read the FIFO. Small fix: reject every unsupported nonregular entry before source reads; preferably use one `lstat` result for explicit file-type decisions. Test FIFO and Unix socket where supported, plus an ordinary valid directory control. A static result remains `verified=False` under all cases.

## Inspected mechanisms and evidence limits

| Surface | Assessment |
|---|---|
| `compute/rmsnorm.py` | Bounded CPU FP32 semantics, independent Python-float/`fsum` oracle, unrounded float64 comparison, frozen tolerance, exact logical-byte hashing, signed-zero preservation, subclass/nested-tensor denial and external-storage overlap checks. Observation owns detached metadata. Its explicit executable-provenance disclaimer must survive adapters. No additional reproduced defect found. |
| `compute/attention.py` | Scalar/eager/SDPA comparison and cached absolute positions agree by construction of distinct mechanisms. Physical GQA expansion and full tensor ledgers are teaching/reference choices. This is not a bounded hostile-input service or GPU kernel implementation. |
| `compute/cache.py` | Prefix hashes include parent plus complete model/tokenizer/template/adapter/namespace/layout/dtype; pinned pressure rolls back; returned records and trace are detached. Correctly labeled synthetic full-block model. |
| `compute/trajectory.py` | Exact sampled/training IDs, observation-excluding action mask, lag/provenance checks and finite ratio/objective checks are implemented. This is offline arithmetic; no optimizer, training or actual sampled-token evidence is supplied by the code. |
| `compute/cuda_benchmark.py` | Explicit unavailable/unsupported outcome, no fallback, correctness before timing, output release between samples, allocator baselines/deltas and declared timing exclusions. Hardware remains unmeasured. This benchmark runs trusted Python functions; it cannot be used as an independent generated-CUDA receipt writer. |
| `evals/manifest.py`, `analysis.py` | Frozen canonical payload, complete task×trial×arm assignment, matched bases/graders, all-assigned denominator, append-only full snapshots, monotone consumed resources, explicit missing/Unknown, whole-task exclusions retaining spend, paired task/repository resampling. Receipt strings are explicitly unauthenticated by this arithmetic layer; the future adapter must establish provenance. R1/R2 are validation defects within that scope. |
| `evals/allocation.py`, `simulation.py` | Explicit role reserves, settled/reserved/Unknown floor, deterministic allocation and fixed synthetic capacity; DAG dependency/resource predecessors and full open-loop arrival stream; tool return rebuilds generated history after prefix eviction. These do not replace runtime admission/authority or measure service latency. |
| Registry/manifests/evidence | `validate_assets()` passed for42 tasks/82 files. All42 entries explicitly disallow held-out eligibility and belong to `synthetic-issue-tracker-v1`; six calibration plus36 diagnostic. The historical control report contains42 valid correct/unchanged/plausible-wrong controls, all labeled trusted fixture host execution. This audit parsed those records, not reran all controls or converted them into fresh measurement. |

Manifest SHA256: `e17393f9a747f1ff2a5864925b4df0485a05bc1ae190db287cf6be39ca2c1685`. Asset-lock SHA256: `12f8b283e710e7e920395301826ceed61c5a019998b8ab39f911a7e11e4968e4`. Historical control-report SHA256: `5efd2b288554c6728664104d1c901cd2d22739ffee7d2030ffc4d61d0ff30b88`.

Historical `evals/reports/synthetic-reference-demo.json` contains48 assigned rows,38 outcome records,33 accepted synthetic rows,10 missing and5 Unknown. It predates subsequent fixes and cannot establish current-source correctness. `linux-verifier-reference.json` is a separate external-grader record with explicit containment limitations. Dated reports remain preserved.

## Smallest next adapter contract — proposal, not implementation

**Purpose.** Convert one declared local development evidence window into immutable, inspectable failure observations and reviewed regression proposals. Reuse `service.artifacts` canonical/digest encoding, existing RuntimeStore snapshots/committed events, scoped artifact reads, registry controls and `FrozenManifest` identities. No scheduler, authority table, automatic retry, evaluator or trainer is added. Start with exact failed-verification records and Unknown dispatch records; heuristic expensive-run grouping and all other miners can follow independently.

**Ownership.** RuntimeStore remains authority for committed events, task/attempt/candidate/verification/billing state. Artifacts owns bytes. `evals/evidence.py` owns a pure projection and validation contract. `evals/regressions.py` owns immutable regression proposals and exact review records. The caller supplies the declared development window/assignment mapping and authorized source-root/artifact resolver. The adapter cannot turn a local JSON file into authenticated authority merely because its hash matches.

Suggested APIs, to freeze before coding:

```python
extract_failure_evidence(snapshot, events, *, assignment, lineage,
                         source_provenance, window, artifact_reader) -> FailureEvidence
freeze_regression_case(evidence, *, fixture_ref, predicate_id, precondition,
                       controls, source_hashes, fix_revision=None) -> RegressionCase
record_regression_review(case, *, reviewer_id, reviewer_kind,
                         disposition, reasons, reviewed_at) -> RegressionReview
```

Records should be canonical immutable payloads/digests using existing artifact helpers. `FailureEvidence` binds schema, source snapshot/event-bundle hashes and provenance, tenant/task/run/generation/attempt/dispatch, optional frozen manifest+row+submission identity, exact base/candidate/grader/environment/contract, terminal category, trace coverage/invalid reasons, all-role consumption/exposure, lineage and transformation/redaction provenance. Explicitly null unavailable identifiers with a reason; do not invent assignment/model/build IDs for numerical observations. A local unassigned run can be diagnostic evidence but cannot become an assigned trial result.

**Consistent source cut.** Bind one service incarnation and task event frontier. Read only committed events through that frontier; bound bytes/pages/events and verify sequence coverage, tenant/task scope and retained-history status. New events after the frontier must not alter the saved observation. Retention gaps, cross-incarnation pages, empty/malformed records, missing referenced artifacts and disagreement between source snapshot and committed evidence are explicit incomplete/invalid results. `compact_report` alone is insufficient because it drops some attempt/dispatch fields. A capture helper must use the existing store's full snapshot and paginated events, without invoking any mutator. The precise stable-read mechanism must be reviewed with the storage owner before calling captured records consistent.

**Identity and accounting.** A failure event must join its exact candidate/tree/grader/environment and task generation. Read scoped artifacts and recompute byte digests, never match basenames or arbitrary paths. Deduplicate dispatch/receipt identities, preserve unresolved effect separately from billing state, and preserve parent/child/planner/integrator/reviewer/retry/summary costs. Runtime budget units must retain their declared unit/rate identity; never relabel generic units as USD. Unsupported/missing token or infrastructure measurements are unknown, not0. Keep assignment inclusion and quality outcome separate from spending. The adapter must not call `record_verification`, `publish_review`, `record_review` or settle billing.

**Regression semantics.** `RegressionCase` binds source evidence hash, fixture hash, explicit precondition/invariant, versioned allowlisted predicate ID, exact known-bad and known-good control evidence, lineage/family/split, review disposition and actual fix revision if known. A predicate is a trusted registry entry, not source text/`eval` or a callable imported from a mined record. Proposal defaults to pending; a model cannot manufacture human review or silently rewrite graders. Automated review may be recorded with `reviewer_kind=ai` and its true scope. All mined cases remain development. Siblings retain the original family and cannot become held-out merely by changing filenames/IDs. No training export or publication is part of this slice.

**Numerical observations remain separate.** NV-S0 observations can later be attached as `evidence_kind=local_cpu_numerical_observation`, with executable identity absent and no task-acceptance field. They are neither `NumericalReceipt` nor an accepted outcome for `analyze`. Do not route CPU pass into a production verification or acceptance adapter. NV-S1's build/binary/device/measurement contracts must exist before GPU evidence can be joined.

**Distinguishing acceptance controls.** Capture a complete committed failed-verification run and recover the exact identity; change candidate/grader/environment or another tenant's artifact and reject; delete an event/artifact and return incomplete; duplicate a receipt and do not double count; retain Unknown effect with settled bill; preserve parent10+child7+summary3=20 after projection; keep one success plus one infrastructure failure at1/2 assigned while separating conditional quality; accept the correct regression control and reject unchanged/plausible-wrong controls; reject renamed sibling held-out promotion; reject `outcome=pass` CPU observation as accepted execution evidence. Fresh regression execution, if later selected, uses the existing isolated runner and fresh workspace, not historical tool-output replay.

**VI:** Adapter chỉ nối evidence đã có với identity đúng. Ví dụ verifier fail cho candidateA thì record phải giữ A, grader và environment đó. Đổi sang candidateB không được tái dùng verdict. Tiền Unknown vẫn tồn tại, kể cả khi chọn trace ngắn để đọc. Regression là development data; chưa có review thì ghi pending.

## NVIDIA/course fit and sources

The existing course-derived ordering already puts local evidence/regressions before context/skills/LSP. The NVIDIA plan explicitly reuses that foundation for NV-S4 while allowing separate NV-S1 boundary design. Therefore no broader refactor, second evaluator, public benchmark migration or training system is justified by this audit. The most useful present work is verified defect repair; the adapter remains the smallest next feature after its source capture, accounting units and review contracts are frozen.

Fresh primary-source check on **2026-10-10**: [NVIDIA ComputeEval README at pinned commit00fbad91](https://github.com/NVIDIA/compute-eval/blob/00fbad91b63957a002b501f33a06510cd25beaae/README.md) separates generation-visible context from evaluator tests/reference and describes optional GPU performance measurement. This supports keeping correctness, visibility and performance evidence separate; it does not establish this project's isolation or independent timing. The [NeMo Agent Toolkit evaluation URL](https://docs.nvidia.com/nemo/agent-toolkit/latest/workflows/evaluate.html) returned no readable body in this check, so no new claim is based on it. The parent audit separately checks current CUDA and agent-evaluation primary sources. Course alignment here relies on the existing [pinned source audit](course-audit-2026-10-10.md), not a fresh upstream-code claim.

**Exit evidence:** three minimal adversarial reproductions plus asset/lineage validation above. No full-suite result is claimed by this read-only audit. Integration owner should repair accepted findings with regressions, run the relevant modules once, then retain source-bound verification. All human mastery fields remain untouched.
