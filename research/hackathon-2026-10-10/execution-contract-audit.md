# Execution contract audit: supported repository repair

**2026-10-10; AI-authored static design audit.** This file is a bounded execution contract for the existing hackathon S1–S5 slices, subordinate to the canonical capstone contracts and current human instructions. It does not introduce a second project, runtime, curriculum or evaluator. No source code, tests, provider calls or deployments were changed or run for this audit. Coordinator-frozen decisions are identified below; remaining names/interfaces are integration proposals until aligned with the owning component specification.

The current instruction removes the assumed four-hour daily build limit. Continue authorized engineering by dependency and evidence gates. It does not supply account access, an inference spending ceiling, hosting funds, eligibility facts or permission to publish/send messages. The four-hour/80-hour schedule is historical planning, not a stop condition. Older learn-before-build text in capstone chapters 03 and 06 is superseded by AGENTS.md/current preference and chapter 04's build-first clarification. Human mastery remains separately unassessed.

**VI:** Không giới hạn giờ build mỗi ngày nghĩa là tiếp tục làm các phần engineering đã được giao. Nó không tự điền budget hay biến mock thành model thật. Điều kiện dừng đúng là thiếu input thực sự cần thiết hoặc invariant chưa đạt, không phải hết bốn giờ giả định.

## 1. Decision and inspected authority

Build one supported, oracle-free repair path around `RuntimeStore`, `Harness`, native Nebius continuation, guarded `Workspace`, `DockerSandbox`, existing candidate/integration transitions and existing reporting/evaluation records. Keep `ReferenceEngine` and its exact fixture guards unchanged. A new coordinator assembles these same primitives; it is not a second durable runtime. First prove read → edit → developer test → immutable candidate → fresh independent verification → review artifact using an explicitly injected mock model transport. Then run actual sponsor inference only under a complete operator-approved configuration.

The irreducible constraints are: inference is a fallible proposal; external effects do not commit atomically with the authority database; a test result belongs to exact bytes; and unknown charges remain possible after a lost response. Consequently, success cannot be a model sentence, a process exit code or a saved conversation. It must be a passing trusted receipt for the current tree and frozen grader/environment, followed by a deadline-valid publication transaction.

**VI:** Ta không cần thay ledger/harness để nhận repo mới. Phần mới là nối issue và snapshot thật vào loop, rồi nối candidate vào một grader có contract riêng. Nếu sửa guard của fixture, ta làm mất bằng chứng cũ mà vẫn chưa có runner tổng quát đúng nghĩa.

Audited inputs: AGENTS.md; `context/current-state.md`; selected `study/packets/H0-reference-runtime.md`; all capstone chapters 01–08 and README; all hackathon files; same-day architecture/provider/Nebius/plan-review evidence; `research/course-audit-2026-10-10.md`; relevant course-derived extension sections of capstone 07. Existing dated research owns its web-source findings; this audit did not re-fetch sponsor rules or prices. Canonical requirements remain SYS-01–12, RT-01–12, EV-01–08 and OP-01–08 within their declared profiles.

| Existing source seam, inspected at audit time | Consequence |
|---|---|
| [Fixture guard and oracle read](../../service/engine.py#L66) | The existing engine is valid mechanics evidence only; new runner must have no import/read dependency on `workloads/oracle` or a reference patch. |
| [Harness run](../../service/harness.py#L103) | Reuse protocol, billing, durable intent, tool results and checkpoint loop; inject the supported model adapter and developer-test callback. |
| [Broker test callback](../../service/harness.py#L52) | `run_tests` already has an insertion seam, but test-count limits and physical environment admission must be supplied by its trusted supervisor. |
| [Workspace](../../service/execution.py#L41) | All materialized files are readable; only `allowed_paths` are writable. Thus protected assets must never be materialized in the worker root. |
| [Linux verifier](../../service/verification.py#L121) | Existing verifier supports exactly the issue-tracker protocol. Reuse containment and external-grader pattern, not its claim for unrelated repositories. |
| [Replacement claim](../../service/storage.py#L532) | Existing authority already rejects replacement while prior physical environments or uncertain effects remain. |
| [Checkpoint reconstruction](../../service/recovery.py#L34) | Reconstruction checks generation/frontier and yields data, never authority. |
| [Report projection](../../service/reporting.py#L11) | Extend a derived view; the current HTML contains fixture-specific wording that must become evidence-kind dependent. |
| [Accepted endpoint](../../evals/analysis.py#L38) | Preserve real review requirements; add a separately versioned verified-repair bridge rather than fabricate acceptance. |

Source anchors describe the inspected baseline; subsequent implementation can move declarations. The delivery record must refresh anchors and capture source hashes, rather than claim this static audit tested new source.

## 2. Frozen data and ownership

An initial supported task consists of a bounded UTF-8 snapshot, one behavior issue, read-visible files, immutable edit allowlist, a preinstalled pinned Python/Linux recipe, visible developer cases and separately protected final cases. No arbitrary archive extraction, repository startup hook, online install, model-selected command, mutable branch reference, symlink, binary, submodule or generated grader is admitted. A Git source may be supplied only with an exact commit and selected file manifest; reject dirty selected files for this first profile. A non-Git authored snapshot uses `base_git_commit: null`, explicit provenance and the service text-tree digest; never invent a commit.

Bounds to freeze for the first implementation: at most 50 files, 256 KiB total UTF-8 source, no file above 64 KiB, one static patch node, at most 12 model turns across all attempts, at most four worker-test dispatches across all attempts, serial tools, one normal final verification, and two patch attempts only when S4 recovery is enabled. File addition/deletion and rename are initially unsupported because the existing edit tool only replaces text. Limits are configuration, not measured provider capacity. CPU/container defaults can reuse the current supported `DockerSandbox` envelope; exact image ID/architecture and timeout/output/resource policy enter the environment digest.

**VI:** Allowlist ghi được và manifest đọc được khác nhau. Nếu hidden tests nằm trong thư mục workspace, `read_file` vẫn có thể đọc dù không được sửa. Vì vậy tách grader về owner và bytes, không chỉ đặt file read-only.

Proposed Python-facing intake schema (strict validation, JSON-safe frozen representation; names may be aligned once with the coordinator):

```python
RepairTaskSpec = {
    "schema": 1,
    "task_definition_id": str,
    "repo_id": str,
    "base_git_commit": str | None,
    "issue": str,
    "source_paths": list[str],
    "allowed_paths": list[str],
    "recipe_id": "python-json-function-v1",
    "recipe_digest": str,
    "visible_case_ids": list[str],
    "limits": {"max_files": 50, "max_file_bytes": 65536,
               "max_total_bytes": 262144, "max_turns": 12,
               "max_worker_tests": 4},
}
# Prepared manifest adds exact files/individual byte digests, base_tree_digest,
# task-spec digest, recipe/grader/environment digests and preparation provenance.
# Operator run configuration adds provider approval identity, rate snapshot,
# absolute execution/review deadlines and integer micro-USD ceiling.
```

Reject unknown fields, duplicate JSON keys, nonfinite/bool numeric values, duplicate/noncanonical paths, allowlist outside source manifest, malformed digests and recipe/model mismatch before dispatch. Operator configuration owns model/endpoint/key/rates/ceiling; task text and repository files cannot override these. An intake object may declare which supported recipe it requests, but only the trusted registry selects executable code and protected checks.

**Coordinator-frozen metadata strategy:** add a strictly validated optional task-contract `repair_spec` object containing exactly `schema=1`, `input_digest`, `repository_digest`, `recipe_digest`, `provider_digest`, `max_turns`, `max_worker_tests`, and `context_bytes`. The frozen input combines `FrozenRepository.as_dict()`, `PythonFunctionRecipe.as_dict()` and public provider configuration; canonical digest is computed before submission. The input is stored after submission under tenant/task scope in a separate supervisor-only `LocalArtifacts` root named **`control-inputs`**. This root is never passed to the public API artifact backend. The runner loads by frozen `input_digest` and rechecks every component digest and limit before model/candidate execution. No raw source or private cases are embedded in the task contract, avoiding both context duplication and private-case leakage through `project_context`.

The private input includes protected expected cases, so it must **never** be uploaded to normal task artifacts or registered as a public downloadable reference. Only public source/worker description and redacted evidence enter the ordinary artifact root. Final public receipts expose case IDs/digests/pass/categories without protected input/expected/actual values. The provider receives issue plus public case text only; candidate containers receive source and the current RPC input, never private expected values or the full input record. Reports do not serialize the private input or an artifact path that exposes it. Add a sentinel-secret test proving no protected expected marker appears in model requests, public snapshots/artifacts, reports, candidate files or API artifact responses.

This is an additive JSON contract change, not a SQL schema migration. Old readers/writers must fail explicitly if they cannot interpret the profile. Private input writes are immutable; reprepare under the same submission identity must produce identical bytes/config/deadlines or conflict. A crash between submit and private-input storage yields a visible unavailable-input state, never fallback to the original mutable directory. Reprepare with the same idempotency identity can supply only the identical digest-bound input.

**VI:** Cùng tên task nhưng source hoặc recipe khác là input khác. Artifact hash chỉ xác định bytes; caller scope và trusted registry mới cho biết ai được dùng bytes đó để làm gì.

| State/object | Owner | Required identity and invariant |
|---|---|---|
| Prepared source | Trusted intake + immutable artifact store | File bytes/path manifest and `base_tree_digest`; subsequent source mutation cannot affect run. |
| Task authority | Existing `RuntimeStore` | Tenant/task/generation/contract digest; `patch_slot_limit=1` only for repair profile; default remains two. |
| Provider configuration | Operator gateway | Provider, protocol, endpoint, exact model, approval/capability revision and envelope; secret stays outside manifests/containers/reports. |
| Transcript and model receipt | Harness + artifacts | Exact request and raw entity bytes; opaque native assistant content and linked tool results retained. |
| Workspace/effects | Broker + current owner | Digest-checked edits; known results replay; unresolved effects cannot repeat. |
| Worker tests | Trusted test supervisor | Test ordinal, exact input tree, visible recipe, environment reservation, bounded observation and retirement. |
| Final verdict | External verifier supervisor | Exact tree/grader/environment/contract identity; expected answers and receipt creation outside candidate execution. |
| Report/diff | Derived evidence projection | Cannot grant authority, settle a charge, synthesize a verdict or mark human acceptance. |

## 3. S1–S2: recipe, runner and independent checks

Freeze the first recipe in **`workloads/repair/recipes/python-json-function-v1.json`**; task descriptors in **`workloads/repair/tasks/<task_definition_id>.json`**; owned source snapshots in **`workloads/repair/repositories/<repo_id>/`**. These paths are proposed additions, not existing files at audit time. Do not put protected expected outputs or reference patches inside the snapshot manifest. Keep correct/unchanged/plausible-wrong controls in supervisor/test-only assets excluded from worker/context/public-release task input. Protected recipe cases belong in the private `control-inputs` root; any public recipe description contains only allowed developer cases and metadata. Existing synthetic issue-tracker workloads remain a separate preserved population.

The minimal recipe is a fixed Python module/export callable receiving JSON positional/keyword arguments and returning a bounded JSON value or an explicitly enumerated application exception. The trusted registry owns the supported module/export, RPC launcher/version, case list, expected outputs/exceptions, limits and image. A fresh candidate process runs only inside `DockerSandbox`; the host never imports candidate Python. The host sends inputs and reads strict bounded responses, then computes assertions itself. Expected outputs are not sent to the candidate. This supports small utility/service behaviors; it does not claim arbitrary Python service or test-suite compatibility.

**VI:** Candidate có thể trả JSON sai hay in “PASS”, nhưng supervisor so giá trị thực với expected giữ bên ngoài. Ta chấm behavior của API nhỏ đã khai báo; mở rộng sang database/server cần một recipe khác có lifecycle và oracle riêng.

Developer feedback and final verification reuse the same bounded transport but have distinct purpose, case sets and evidence identities. Visible cases may be available to the worker; protected cases stay out of source, provider requests and tool outputs. Never trust candidate-authored JUnit/reward files or exit zero alone. Final checks start from a fresh immutable candidate snapshot after integration. Transport failure is latched independently of application exceptions: malformed JSON, extra stdout, timeout, oversized output, missing response or infrastructure loss cannot pass an expected-exception test. Copy the input mapping before computing its digest and provisioning it, as the existing verifier does.

Minimal public in-process seams:

```python
prepare_repair(repo_root, task_spec, trusted_recipe, output_dir) -> PreparedRepair
RepairEngine(store, artifacts, run_root, trusted_registry, model_factory,
             provider_approvals).submit(prepared, operator_config, tenant, key) -> dict
RepairEngine.run_task(tenant_id, task_id) -> dict
RepairTestSupervisor.run_visible(files, *, owner, ordinal) -> TestReceipt
RepairVerifier.verify(files, task_definition, *, sandbox_id) -> VerificationDetail
write_repair_report(output_dir, snapshot, events, artifacts) -> dict
```

Every workspace read/edit/test enters the existing broker. `model_factory` and recipe/verifier injection are trusted constructor seams used by the CLI/operator/tests; they are never import paths or commands accepted from task JSON. Claim a single `repair` node with the immutable allowlist and feed issue plus source inventory/visible contract to the harness. Do not infer changed paths by diffing against a reference answer. Integrate the returned manifest with `candidate_manifest`/`integrate_candidates`; use existing `accept_candidate`, `integrate`, `record_verification` and `publish_review`. A model stop is only a completion proposal. A failed final verifier yields an explicit candidate failure in v1; another repair attempt needs a later bounded, separately specified control loop.

Worker-test admission uses `reserve_environment` before Docker provisioning, in addition to the patch workspace claim, because the test container is a separate physical resource. Count tests from durable dispatch/receipt state across resumes, not a resettable Python counter. Every test attempt consumes its count, including infrastructure failures; an idempotently replayed known receipt consumes no new attempt. Final verification has its own environment reservation and receipt. Persist owned creation nonce/container identity before destructive cleanup becomes necessary; uncertain create/cleanup retains its slot. A process group dying is not proof a container stopped.

**VI:** Workspace sửa file có thể chỉ là dữ liệu trên host, còn `run_tests` tạo process/container thật. Một slot patch không tự chứng minh đã hạch toán container test; cần reservation và retirement cho từng môi trường vật lý.

S1–S2 distinguishing controls, required before a useful-repair claim:

- Prepare once, mutate original repository, run from prepared bytes: base unchanged; changed input under the same submission key conflicts.
- Reject symlink/absolute/parent paths, excluded files and protected-asset references before model/candidate execution; stale edit digest changes nothing.
- Deny/deinstrument all oracle/reference loading in runner tests; new source and issue must still drive read/edit/test through model responses.
- Mock tool loop reads actual bytes, uses returned digest, edits, runs visible test and finishes; next request carries exact native assistant/result objects.
- Correct control passes; unchanged and plausible-wrong controls fail; empty checks, forged PASS, early exit, malformed response and boundary-failure-as-expected-exception never pass.
- Final receipt for tree A cannot publish tree B; mutated expected tests/recipe/environment reject by digest.
- Fifth worker test refuses before provisioning; timeout/output overflow is bounded; cleanup uncertainty retains slot; no host import/online install occurs.
- Deadline/cancel/stale owner denies candidate/publication even after a test passes; report retains failure and incurred cost.

## 4. Provider admission, exact endpoints and offline E2E

The frozen inference endpoint is **`POST https://api.tokenfactory.nebius.com/v1/chat/completions`**. Account catalog preflight, once configured and authorized, uses **`GET https://api.tokenfactory.nebius.com/v1/models?verbose=true`**. Global-only exact matching remains; regional URL, arbitrary URL, redirects, fallback model and hidden retries remain unsupported. The existing source sends nonstreaming `n=1`, `tool_choice=auto`, `max_tokens`; actual per-model reasoning-inclusive cap and input-bound semantics still require authoritative evidence. Public cookbook defaults or JSON byte length cannot establish a token bound.

Before paid execution, freeze a provider approval keyed by the tuple **(provider, protocol, endpoint, exact model)** plus an approval revision/digest. Bind this identity to the task/run contract and every request. Approval record includes account/catalog evidence, model feature/cap semantics, rate snapshot identity, authoritative bound evidence, approval time, permitted ceiling and disabled/enabled state. Existing `provider_envelopes[model]` is too weak for a generalized operator configuration because a name alone can collide across providers. Preserve the legacy harness behavior for already supported tests if needed, but the new repair path must verify the stronger tuple before any HTTP dispatch. No account-specific values are fabricated.

**VI:** Request log ghi endpoint đúng chỉ chứng minh đã gửi ở đâu; nó không chứng minh operator đã duyệt giá của endpoint đó. Approval phải xuất hiện trước dispatch và khóa cùng provider/model, không chỉ so chuỗi tên model.

For offline E2E, construct the actual `NebiusChatCompletions` adapter with an injected trusted `httpx.Client(transport=httpx.MockTransport(...))` and a synthetic explicitly approved envelope. The current harness requires `model.enabled`; `enable_network=True` in this isolated test permits only the injected transport, so the test must assert the transport is mock and forbid any real socket/network fallback. Label evidence `mock_nebius_protocol_repair`, never live repair. Production CLI constructs no enabled adapter by default. Avoid a user-selectable `--fake-pass`/arbitrary verifier plugin. A scripted model can test lower-level machinery, but the main offline E2E must exercise the real native adapter/harness seams.

A prerequisite hardening slice should preserve bounded non-2xx transport evidence: status, allowlisted request-ID/rate-limit/Retry-After headers, complete bounded body or explicit truncation/transport failure, request identity and timestamp. Never store Authorization/Cookie/key material. Existing `raise_for_status()` happens before body capture, so error diagnostics are currently lost. Persisting error evidence does not authorize tool parsing or imply zero charge. HTTP 429/500, redirects, partial body and lost response execute no tool, retain conservative liability and send exactly one request. Use a typed transport outcome/error carrying evidence; do not overload a successful model JSON result and accidentally allow replay to parse an error as tools.

**VI:** Header request ID giúp hỏi provider chuyện gì đã xảy ra; nó không tự cho phép retry. Cần giữ hai câu hỏi riêng: có response/error gì và có bằng chứng tính tiền đủ tin cậy chưa.

## 5. S3: exact diff and inspectable report

The user-facing report starts with outcome, generated diff, before/after visible-test evidence, independent final result, settled/reserved/unknown money and review state. It links task/base/candidate/grader/environment/contract identities and allows inspection of the relevant tool/model events. Save JSON plus standalone HTML using the existing report path; escape all untrusted strings and never run repository/script content in the report. Downloads are exact UTF-8 unified diff and candidate manifest. Applying the diff to the frozen base must reconstruct the verified tree digest. Unsupported mode/rename/add/delete changes are rejected, not silently dropped.

Report generation from persisted artifacts is read-only and requires no provider secret, model call, candidate execution or re-verification. Fetch every event page rather than assuming 1,000 events is the full history. Missing artifacts, truncated history, pending verification, unsettled charges and unconfirmed cleanup remain explicit. Rendering failure does not rewrite task outcome. A report displayed after a later settlement carries its observation cutoff and references; preserve prior saved evidence. Do not inherit the existing static 'scripted fixture' subtitle for a live/mock repair profile.

**VI:** Report là cửa sổ nhìn evidence. Nó không được tự suy ra pass vì diff đẹp, cũng không được biến Unknown thành zero cost để UI dễ đọc. Test report chính là lần ngược từ câu kết luận về receipt gốc.

## 6. S4: supported checkpoint resume authority

Supported recovery v1 is **process loss after a committed complete-tool-turn checkpoint and before the next dispatch**. Add an explicit controlled pause hook immediately after `store.checkpoint` commits and before the next model dispatch. A supported pause returns its checkpoint ID and records its boundary before the trusted coordinator retires environments; it leaves task generation intact and is not recorded as execution failure. The next process uses the same task/deadline/budget and acquires a new owner. It is neither cancellation nor database rollback. Candidate complete/head complete states reuse accepted artifacts; they must not rerun a finished patch node. A checkpoint after a finish proposal must persist `completion_proposed` metadata and be classified as completed work rather than creating an unnecessary new model call. Current plain terminal provider responses return without a checkpoint; either persist an equivalent terminal continuation before exposing a pause there, or explicitly exclude that crash window from v1. A callback in memory alone does not establish a durable pause boundary.

Recovery sequence:

1. Load the authoritative snapshot and checkpoint from the same tenant/task. Reject cancelled/expired/stale generation, quarantine, incompatible contract/provider/recipe or missing/corrupt artifact.
2. Verify old-attempt dispatch frontier has not advanced and has no in-flight/unknown effects, unresolved call/result pairs or unconfirmed test environments. The initial supported path also requires all model charges settled; broader unknown-billing continuation needs its own bounded rule.
3. Establish prior controller/process termination or an exclusive per-run execution boundary. A file lock/PID is not sufficient proof by itself for remote containers; bind physical-instance observations to creation nonce and immutable ID. Never accept user/model text `retired=true` as observation.
4. Confirm retirement of every owned patch/test physical environment and persist evidence through existing `retire_sandbox`. This fences the old attempt and releases only unused allowance. Do not use `cancel`, which changes generation and makes the checkpoint stale.
5. Reconstruct checkpoint data with `restore_checkpoint`; recheck authoritative state at claim/dispatch. Acquire a new distinct claim ID, attempt and node epoch under the same current task generation and remaining budget/deadline. No reuse of old owner authority.
6. Materialize a fresh workspace from checkpoint bytes; verify exact digest. Continue `Harness.run(..., restored=...)` with native messages/tool IDs/provider evidence and cumulative turn/test limits. A later old owner must fail dispatch, checkpoint and candidate acceptance.

A lost provider response or edit-before-receipt crash falls outside clean recovery: retain Unknown, liability and applicable occupancy; show a reconciliation-required outcome and send no repeated request. Never manufacture `failed_known` or actual cost zero to enable replacement. Database-backup restore remains the distinct quarantined fresh-incarnation runbook, not this command.

**VI:** Checkpoint giống ảnh chụp state đã biết, còn owner giống quyền được thay đổi state hiện tại. Khôi phục ảnh không cấp lại quyền. Nếu effect mới đã xảy ra sau ảnh, quay lại ảnh rồi chạy tiếp là bỏ mất lịch sử; đúng là phải dừng để đối soát.

Fault evidence: two real CLI processes share one run directory; first is interrupted at the committed safe boundary, second obtains a new owner and resumes without repeating known effects. Preserve native continuation equality, old/new owners, original and resumed tree identities, all request counts, spent/exposure and retirement receipts. Separately inject provider response loss and advanced-frontier checkpoints and assert refusal with no new HTTP. Missing retirement, concurrent controller, stale owner, lease expiry, provider change, budget exhaustion and cancelled generation each have a distinct rejection. Resume success with only in-memory dictionaries is insufficient for the process-restart claim.

## 7. S5: CLI/API product and completion criteria

Proposed CLI surface (names are integration inputs, commands are not implemented by this document):

```text
agent-lab repair prepare --repo PATH --task TASK.json --output RUN_DIR
agent-lab repair run --prepared RUN_DIR --operator-config CONFIG.json
agent-lab repair report --run RUN_DIR
agent-lab repair resume --run RUN_DIR             # enabled only after S4 evidence
```

`prepare` validates/freezes inputs without executing candidate code or contacting a provider. `run` defaults to disabled live network and fails before dispatch if account approval/key/ceiling/image are incomplete. Credentials are provided through a named environment variable/server-held mechanism, never CLI argument text or serialized config. The trusted test suite calls injection APIs directly for offline E2E. `report` works without credentials. `resume` verifies supported authority/retirement conditions, then calls the same runner/harness. Existing `demo`, `doctor`, `workloads` behavior remains intact.

No additional HTTP namespace is needed for the first local test build. Reuse actual current endpoints, without inventing the proposed `/v1` prefix: `POST /tasks`; `GET /tasks/{task_id}`; `GET /tasks/{task_id}/snapshot`; `GET /tasks/{task_id}/events`; `POST /tasks/{task_id}/cancel`; `GET /tasks/{task_id}/artifacts/{artifact_digest}`; `POST /tasks/{task_id}/reviews/{review_id}`; `GET /health`. Current task submission alone does not select/execute the new runner: a trusted configured dispatcher/activity registry must route the supported frozen profile to it before an HTTP live-run claim. Final-verifier, resume, price-approval and retirement functions remain trusted internal seams, not model/public-client authority.

**VI:** CLI hoàn chỉnh là product workflow hợp lệ để kiểm local. Có endpoint submit chưa có nghĩa backend đã biết chạy repair profile; cần chứng minh request đi hết đến runner và report. Free judge access và sponsor call thật vẫn là gate riêng.

| Slice | Exit evidence | What can proceed now |
|---|---|---|
| S1 Intake/runner | Strict task/manifest binding, one-node mock-native loop, no oracle reads, source drift/path controls | Implement and validate locally. |
| S2 Tests/verifier | Actual pinned Docker RPC, correct/no-op/wrong/forged controls, physical accounting and independent exact receipt | Implement; run local integration when the pinned image exists. No host execution fallback. |
| S3 Diff/report | Apply diff reproduces verified tree; honest JSON/HTML replay with zero network and full evidence links | Implement alongside S1/S2 once immutable identities agree. |
| S4 Restart | Cross-process clean checkpoint resume with new authority; Unknown stops; no duplicate effects/charges | Implement after S1/S2 and exact physical lifecycle are verified. |
| S5 Delivery | Fresh locked install, functional test build, real sponsor repair, accessible funded judge route, source/license/provenance/setup/video/submission artifacts | Prepare local source/build/drafts now; account/spend/access/publishing facts remain explicit inputs. |

Completion has distinct levels: **offline implementation** (source and distinguishing local checks), **live product** (actual approved NVIDIA/Nebius repair), **submission** (public functioning access and all required materials actually submitted), **operated/research capstone** (its broader measured gates), and **human mastery** (Huy's genuine evidence). A green mock suite completes only its supported engineering level. Remove any unmeasured restart/comparative claim from a release rather than mark it passed. No daily-time assumption gates authorized local work.

## 8. Research and course-extension integration

Retain the existing evaluator/assignment store and all-assigned denominators. Verified repair is a versioned predicate requiring an exact passing receipt and valid publication by the execution cutoff; accepted additionally requires actual human review under its separate rule. Never fill fabricated reviewer/time fields to satisfy `evals.analysis.accepted`. The small hackathon comparison remains descriptive and conditional on approved spend; do not silently replace the broader role-aligned 1/2/4 study or create a second evaluator. Preserve calibration versus held-out boundaries and every assigned failure/Unknown.

Course-derived failure-to-regression evidence can be implemented after the core repair path, reusing real immutable traces and known-wrong controls. Accepted context projections must change actual request construction and survive fenced activation; a pure helper is not enough. Skills require immutable package identity and broker-bounded access; LSP requires a supervised process recipe and freshness/encoding identities. These extensions remain bounded additions within existing contracts; none is necessary to declare a basic supported repair working, and none replaces S1/S2, independent checks or live sponsor conformance.

**VI:** Điều đáng học từ course là cách biến failure thành test phân biệt được, rồi đo một thay đổi. Không cần copy stack khác để có compaction/skills/LSP. Phần lớn giá trị nghiên cứu đến từ phép đo có authority đúng, không phải số feature trong README.

## 9. Integration risks to resolve before claiming success

1. **Manifest authority:** enforce the frozen `repair_spec` component digests and private `control-inputs` separation; eliminate mutable source/recipe side channels and keep old-reader compatibility explicit.
2. **Physical lifecycle:** persist test/final-verifier identities and retirement through exceptional paths; uncertain provisioning or cleanup cannot release capacity.
3. **Whole-run limits:** turn/test/attempt/token/deadline ceilings survive a fresh process. Harness per-call defaults alone do not establish all-attempt limits.
4. **Provider approval:** tuple-keyed approval and transport error evidence precede enabled paid repair; bound evidence and authorized total spend remain missing external inputs.
5. **Trusted injection:** mock adapter/test supervisor injection is an internal seam; product input cannot select arbitrary Python code or report its own verifier verdict.
6. **Measurement honesty:** mocked native repair, actual Docker verification, paid live repair, human acceptance and human mastery carry different evidence labels.
7. **Release scope:** preserve historical source/runs and personal learning material; curate product distribution and required third-party notices. Draft packaging is not public publication or submitted status.

Audit outcome: no fundamental need to replace the existing runtime. The immediate engineering blockers are precise supported intake/recipe contracts, one oracle-free coordinator, durable test-environment lifecycle, and operator-bound provider preflight. S1–S3 can be completed and fault-tested offline; S4 then needs actual cross-process evidence. The account/spend/judging-access gates remain visible rather than blocking unrelated authorized source work.
