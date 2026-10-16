# Run and inspect the supported repair reference

Implemented 2026-10-10 under Huy's instruction to build continuously by acceptance gates. This is a supported single-module, standard-library Python function repair path using the existing RuntimeStore/Harness. The native provider interface is ready for approved Nebius configuration. Current completed demonstrations use an explicitly mocked provider and real local Linux containers; no NVIDIA reasoning/coding-quality result is inferred.

## Delivered path

| Component | Inspected source | Evidence and boundary |
|---|---|---|
| Frozen source intake | [freeze_repository](../service/repositories.py#L290) | Declared read paths, writable subset, immutable bytes, optional selected-file Git provenance; no arbitrary directory upload |
| Provider approval | [ProviderApproval](../service/repair_provider.py#L37) | Frozen provider/protocol/endpoint/model/rates/bounds; mock client cannot fall through to live HTTP |
| Private recipe | [PythonFunctionRecipe](../service/repair_verification.py#L155) | Public cases projected to worker; full private inputs stored outside normal task artifacts/API scope |
| Independent execution | [PythonFunctionVerifier](../service/repair_verification.py#L268) | Fresh Docker container per case; host comparisons, strict protocol, exact identities and retirement |
| Repair coordinator | [RepairEngine](../service/repair.py#L49) | One oracle-free patch node, current workspace tests, exact candidate/final verdict, existing budget and slot admission |
| Recovery | [run_task](../service/repair.py#L183) | Native clean checkpoint; new owner/epoch; cumulative bounds; global frontier and billing reconciliation guards |
| Report | [write_repair_report](../service/repair_reporting.py#L218) | Exact stored diff, identity-matched verdict, offline HTML/JSON, pending human review, hostile-text escaping |

The fresh-container recipe runs stateless JSON functions only. It does not install dependencies, run arbitrary repository shell commands, load generated Python into the supervisor, or support GPU builds. Semantic compaction and LSP remain proposed. Immutable skills with accepted disclosure and typed recovery are delivered as a separate optional profile; the default repair path does not automatically gain that profile. NV-S0 CPU semantics and a trusted authored GPU qualification probe exist, while generated-GPU execution and profiler/intervention work remain separate gaps. See [current readiness](../research/system-readiness-plan-2026-10-11.md). The existing scripted issue-tracker engine and its prior evidence are preserved.

**VI:** Module mới nối runtime vào một loại repository có contract rõ. Source có thể được model thật sửa sau khi cấu hình account/budget, nhưng việc chứng minh reasoning bằng model thật là gate riêng. Không biến authored demo thành benchmark thực tế.

## Reproduce the completed local demonstration

From this workspace, use an already present immutable Python Linux image. The measured local image is `sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9`, arm64 Linux. Another machine needs its own already present image and environment identity; this command does not pull an image.

```sh
.venv/bin/python -m service.cli repair-demo \
  --output runs/my-supported-repair \
  --sandbox-image sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9
```

Outputs: `repair.html`, `repair.json`, `change.patch`, `snapshot.json`, `trace.json`, `trace.html`, task-scoped public artifacts, private `control-inputs`, database and saved task identity. The worker root contains only declared source. The full expected-output recipe is never materialized into it. Keep control-inputs private; public release packaging must not include run directories/private inputs.

Measured uninterrupted run: five native mock requests, two worker-test dispatches, three separately admitted verifier evaluations, one patch attempt, exact final pass and all slots retired. Human review is pending. Settled/reserved model cost is zero because the mock uses synthetic zero rates; local container/infrastructure cost is not measured by that token ledger.

**VI:** “Zero” ở ledger là chi phí model giả trong fixture, không có nghĩa compute/container miễn phí. Test trước edit thất bại, test sau edit và final checks dùng candidate thật trong Docker; mock chỉ quyết định các tool proposal.

## Reproduce a clean process restart

```sh
.venv/bin/python -m service.cli repair-demo \
  --output runs/my-supported-restart \
  --sandbox-image sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9 \
  --pause-after-turn 2

.venv/bin/python -m service.cli repair-demo \
  --output runs/my-supported-restart \
  --sandbox-image sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9 \
  --resume
```

The first process commits a checkpoint, removes its controlled text workspace, retires its patch grant and exits. A second process reloads exact native messages/files and obtains epoch2. Measured resumed run: two requests before pause plus three after; total five, with two attempts and the same two worker-test dispatches/three verifier evaluations. Turn/test allowances and spending survive restart. Old ownership is fenced. A completion-proposed checkpoint finalizes the candidate without another model call.

Known final receipts also survive a publication/failure-write interruption: the runner reuses the exact saved receipt instead of rerunning checks. A dispatch after the selected checkpoint in any attempt, unresolved billing, an Unknown effect or uncertain environment retirement refuses resume. Cancellation remains authority revocation, not pause.

**VI:** Chỉ pause tại boundary đã commit và đã biết cleanup. Nếu attempt B có effect mới rồi mất checkpoint, không được quay về checkpoint của A. Guard so toàn bộ dispatch frontier của task, không chỉ attempt tạo checkpoint.

## Configure a genuine provider run

1. Select an authorized supported repository, explicit source/writable paths and the versioned function recipe. Check base/control cases before generation.
2. Obtain actual account catalog/model identity and trusted rate/input/output-bound evidence. Create a public `ProviderApproval` record with `evidence.kind=operator-verified` and source identity. This field is an operator assertion, not automatically obtained proof. Unknown rates or reasoning-inclusive cap semantics must be resolved before enablement.
3. Freeze a total micro-USD ceiling and absolute execution/review deadlines. `repair-prepare --help` lists the required files/fields. Preparation records immutable private inputs and task digests without an inference request.
4. Keep the credential in server-held `NEBIUS_API_KEY`. `repair-run --output <prepared-run> --enable-network` is an explicit network opt-in; without it the CLI refuses. No key is written into approval, model payloads or reports. The mock profile refuses ordinary/live clients even when enablement is requested.
5. Inspect diff, exact verification and uncertainty; supply a genuine human review separately. Do not promote one authored task into held-out performance evidence.

No paid call, account discovery, hosted deployment or public submission was performed. Huy explicitly keeps paid execution disabled for now. Available credits and permitted spend are still unset. The later [HTTP evidence slice](06-http-error-evidence-contract.md) now preserves bounded sanitized non-success diagnostics and prevents tool/usage authority or replay; [current verification](../research/hackathon-2026-10-10/http-error-verification.json) records its integrated checks. Live account/model/rate/bound inputs and a changed spending instruction are still required before paid execution.

## Report replay and verification

```sh
.venv/bin/python -m service.cli repair-report --output runs/my-supported-repair
```

This reconstructs the report from public committed state/artifacts, without provider construction, private recipe loading or a model call. Export follows cursor pages through the exact snapshot frontier and rejects missing prefixes/gaps/duplicates. A matching failed/error receipt remains displayed after failure revokes the task generation; historical passing receipts cannot revive verified status.

The generated patch was checked through independent `git apply` reconstruction for absent final newline, CRLF, Unicode separators, empty/nonempty files and ordinary multiline changes. The report uses stored patch bytes; it distinguishes candidate-only, independently verified and human accepted states.

Review findings and measured reviewer checks are in [independent review](../research/hackathon-2026-10-10/repair-independent-review.md). [Source-bound repair delivery verification](../research/hackathon-2026-10-10/repair-delivery-verification.json) separately records phased full-suite/Docker/restart results. The [dated HTTP verification](../research/hackathon-2026-10-10/http-error-verification.json) records that delivery’s integrated source and its [source archive — local-only](../docs/github-snapshot.md#omitted-local-evidence) and [wheel — local-only](../docs/github-snapshot.md#omitted-local-evidence). The wheel was imported from a disposable extracted directory and validated the repair task/recipe plus42 authored fixture tasks/82 locked assets. Earlier packages/exports remain dated snapshots; their recorded unrelated NVIDIA CPU-source drift does not describe this refreshed export.

## Boundaries retained

The existing CLI clean-pause path remains the demonstrated restart. The later explicit `environment_backend` engine option now adds a write-ahead per-case journal and [bounded physical cleanup](../ops/runbooks/environment-reconciliation.md) after process loss. Default unjournaled runs are not adopted. There is still no automatic task-recovery supervisor: Unknown effects/bills, checkpoint frontier and fresh ownership must be resolved separately. Container cleanup alone never authorizes continuation.

The current interface is CLI/test-build plus offline reports. Hosted repair API admission, public judge access, licensing/public source, public video, actual NVIDIA-model conformance and held-out repairs remain release gates. Existing PostgreSQL/Temporal source is retained; this slice's new core repair tests use SQLite and real local Docker. The app browser rejected local-file URLs during visual QA; structure/download/escaping checks passed, but rendered browser layout was not inspected and no bypass was attempted.

**VI:** Giữ Unknown và giữ slot là hành vi đúng khi evidence chưa đủ, nhưng chưa có nghĩa đã tự động recovery được container đang chạy. Phạm vi đo phải ghi chính xác: local execution, clean restart và artifact replay đã có; live model, hosted access và production operation vẫn cần gate riêng.

## Current offline installed candidate

Use the [release index](../releases/README.md) and [shipped offline guide](../release/OFFLINE.md). [Current rc4 verification](../research/provider-qualification-verification-2026-10-11.json) binds163 curated entries and full independent installed acceptance on this Mac, adding qualification commands to the prior repair/context/skills/service/journal/GPU-disabled checks. The preserved [rc2 review](../research/readiness-release-independent-review-2026-10-11.md) binds its earlier161 entries. The preserved October10 candidate retains148 entries and its two historical installed runs. Native mocks plus the existing Docker image reproduce uninterrupted repair, pause2/resume3 with epochs1/2, exact patch application and report replay without dispatch. Context retrieval/recovery and Unknown no-resend/late settlement run separately through the installed package.

Generated private `control-inputs` and local evidence runs remain outside the source archive. Authored registry oracle assets are required controller-owned test data and never enter worker intake. Base installation excludes optional compute/production extras. Public dependency preparation was online; actual build/install/acceptance were offline. Paid execution is disabled; live NVIDIA/Nebius quality, fresh-machine operation, rendered browser QA and public judge access remain pending.

## Qualify the offline protocol against the prepared task

After `repair-prepare`, use [qualification prepare → run → report → handoff](../ops/runbooks/provider-qualification.md). This exercises internal native mocks only and preserves the exact unstarted repair. A valid handoff is advisory; it neither invokes `repair-run` nor substitutes for changed explicit live authorization, actual account/model/rates, a spend limit or useful live repair evidence. Report validation needs matching frozen service source; inspect earlier reports with their preserved candidate.
