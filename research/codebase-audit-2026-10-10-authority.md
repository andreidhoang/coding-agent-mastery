# Authority, API and operations audit — 2026-10-10

Read-only source audit by an AI reviewer. No implementation or historical evidence was changed by this audit. Reproductions used disposable temporary SQLite/artifact/workspace directories and CPU fixture execution; no paid inference, GPU, external deployment or human mastery evidence. This report freezes proposed repair contracts **before implementation**. Source anchors refer to the audited versions identified below, not any later repaired source.

Read context: `AGENTS.md`, `context/current-state.md`, H0 reference-runtime packet, reference specification and coverage register, NVIDIA extension contracts, operations/recovery runbooks, and first-principles mentor skill. The key invariant is that authority may say “this candidate passed this contract” only when the executed grader, requirements, candidate and environment actually match those identities. A digest copied from a requested contract is not evidence of execution.

**VI:** Receipt phải nối được từ bytes thật đã chạy đến contract thật cần kiểm. Nếu coordinator lấy tên grader từ request rồi tự điền vào receipt, database chỉ thấy các field khớp nhau; điều đó chưa chứng minh grader ấy đã chạy. Audit này kiểm đường nối đó, không đánh đồng green tests với hoàn thành NVIDIA plan.

## Findings and frozen repair contracts

### A1 — P1: fixture coordinator can publish a pass under unexecuted requirements/grader identity

**Verified source:** [`engine.py:70` — local-only](../docs/github-snapshot.md#omitted-local-evidence) selects a workload by repository suffix. [`engine.py:73` — local-only](../docs/github-snapshot.md#omitted-local-evidence) checks only base tree and environment. [`verification.py:103` — local-only](../docs/github-snapshot.md#omitted-local-evidence) executes `task_definition.requirements`, regardless of the submitted contract's requirements. [`engine.py:216` — local-only](../docs/github-snapshot.md#omitted-local-evidence) records the contract's grader/environment and a locally recomputed tree instead of checking the verifier's returned identities. [`storage.py:1243` — local-only](../docs/github-snapshot.md#omitted-local-evidence) correctly checks its supplied arguments against the frozen contract, but cannot repair false attribution by its trusted caller. The CPU verifier returns tree/environment, but no grader identity at [`verification.py:109` — local-only](../docs/github-snapshot.md#omitted-local-evidence); the Linux verifier already returns all three at [`verification.py:265` — local-only](../docs/github-snapshot.md#omitted-local-evidence).

**Measured:** take a valid T3 fixture contract, change only its requirements and grader digest, submit it and execute the normal runner. It completes `review_eligible`. The passing receipt says grader `8bce5d58613c31b5e8cd750a99793e6a83cb153bc7af5e6f20f6622cf6765235` while the selected executed grader is `4174c11b124f6a6206a86e3b45139d4298f86781c7db2430e894e3689755c390`. Its submitted requirement, “Also solve an entirely different requirement”, is not what the workload grader evaluated. These are ordinary valid contract fields, also accepted by the configured API; no private DB mutation is necessary.

**VI:** Ví dụ em yêu cầu kiểm B, nhưng runner vẫn kiểm fixture A. Sau đó nó ghi tên B vào kết quả của A. Đây là false acceptance trong reference fixture path; không phải bằng chứng rằng candidate vượt qua sandbox hay giả được quyền verifier.

**Repair purpose and owners:** the fixture engine owns mapping a supported frozen contract to an exact registry workload; the verifier owns measured identities; RuntimeStore continues owning admissible transitions. Add narrow validation at those two engine boundaries; no new store authority or schema is justified.

**Preflight contract:** before graph creation, claims, dispatches or verifier invocation, require exact supported model/repository, registry baseline tree, registry ordered requirements, registry grader digest and configured verifier environment to match the frozen contract. Reject mismatch explicitly. Existing terminal `review_eligible` replay remains a receipt-only read: preserve the current early return so inspecting a previously accepted result does not rerun or reinterpret it using current registry state.

**Receipt contract:** both verifier implementations must return their actual tree, grader and environment identities on each supported outcome path. After physical cleanup handling, validate a strict boolean `passed` and exact returned identities against the admitted head/contract before authoring a receipt or publishing review. Missing/mismatched identities fail closed. Do not overwrite conflicting returned values with contract values. Preserve any raw verifier evidence and confirmed cleanup; a mismatch must not create a passing receipt. Unsupported/failed CPU outcomes also need complete consistent identity metadata if the engine records them.

**Distinguishing tests:** independently mutate requirements and grader digest; assert rejection with zero nodes, attempts, dispatches, candidates and verifications. Use a verifier spy to assert no invocation. With a valid contract, inject a returned wrong/missing tree, grader or environment, and invalid `passed`; assert no passing receipt/review while confirmed physical cleanup is retained. Keep real 1/2/4-worker happy paths and completed-head resume passing. Reinvoke a terminal task after registry/verifier drift and assert unchanged receipt-only historical snapshot behavior. Test failure/unsupported result branches, not only pass.

Reproduction executed with `.venv/bin/python` from the project root:

```python
import tempfile
from pathlib import Path
from service.artifacts import LocalArtifacts, digest_json
from service.storage import RuntimeStore
from service.engine import ReferenceEngine
from workloads import list_tasks, load_task

with tempfile.TemporaryDirectory(prefix="audit-engine-") as directory:
    p = Path(directory)
    artifacts = LocalArtifacts(p / "artifacts")
    store = RuntimeStore("sqlite:///" + str(p / "state.db"), artifacts)
    engine = ReferenceEngine(store, artifacts, p / "workers")
    source = engine.submit_fixture(list_tasks(tier="T3")[0].task_id, key="normal")
    contract = dict(source["contract"],
                    grader_digest=digest_json("not-the-selected-grader"),
                    requirements=["Also solve an entirely different requirement"])
    task = store.submit("demo", "mismatched-grader", contract)
    snapshot = engine.run_task("demo", task["task_id"])
    actual = load_task(contract["repo_id"].split(":", 1)[1]).as_dict()["grader_sha256"]
    print(snapshot["task"]["execution_state"])
    print(snapshot["verifications"][0]["grader_digest"] != actual)
    store.close()
# Observed before repair: review_eligible; True
```

### A2 — P2: oversized integer deadline produces HTTP 500

[`contracts.py:91` — local-only](../docs/github-snapshot.md#omitted-local-evidence) passes any Python integer into `math.isfinite`, which raises `OverflowError` for a large JSON integer such as `10**400`. The API parses this finite integer successfully, but its ValueError handler at [`api.py:187` — local-only](../docs/github-snapshot.md#omitted-local-evidence) does not catch OverflowError. **Measured:** authenticated `POST /tasks` with `execution_deadline=10**400` returns `500 Internal Server Error`; no task commits. This is an input-validation/error-classification defect, not an authority bypass.

**Repair contract:** timestamp validation owns conversion to representable finite nonnegative UTC seconds. Reject unrepresentable integers and platform/date conversion overflow as ValueError. Do not truncate, saturate or accept infinity. Add a direct timestamp test and API test expecting structured 4xx plus no task/outbox/event creation. Cover both deadline fields, valid finite boundaries and booleans. No general exception-swallowing API middleware is needed.

**VI:** JSON integer có thể hữu hạn theo toán học nhưng vượt miền float mà timestamp implementation dùng. Input validator cần xử lý đúng ranh giới biểu diễn; không cần nới contract hay giấu mọi lỗi server bằng một catch-all.

Reproduction: create a temporary RuntimeStore and TestClient with `raise_server_exceptions=False`; configure token `test-only-token-abcdefghijklmno` for `Principal('tenant', 'user', frozenset({'fixture'}))`; POST `{key: 'large', contract: {repo_id: 'fixture', base_revision: tree_digest({'a.py': 'old'}), requirements: ['change a'], execution_deadline: 10**400}}`. Observed status/body above. Token is a disposable authored fixture, not a credential.

### A3 — P3: recovery guidance recommends reacquisition for a terminal failed task

[`recovery.py:19` — local-only](../docs/github-snapshot.md#omitted-local-evidence) handles cancelled/review-eligible terminal tasks, but omits `failed`, introduced by [`storage.py:1574` — local-only](../docs/github-snapshot.md#omitted-local-evidence). **Measured:** create a task, call `fail_execution(..., 'infrastructure_failed', {'observed': 'fixture failure'})` without effects/environments, then `recovery_plan(store.snapshot(...))`: state is `failed`, next step is `reacquire_owner_then_restore_valid_checkpoint`. `_eligible` at [`storage.py:337` — local-only](../docs/github-snapshot.md#omitted-local-evidence) correctly rejects that recommendation.

**Repair contract:** diagnostic recovery plans must reflect current terminal execution states; terminal failure grants only settlement/inspection obligations and cannot recommend another claim for the same task. Preserve precedence of quarantine, unknown effects and retained environments. Add failed-without-obligations and failed-with-unknown/retained tests. This helper does not execute recovery, so impact is misleading operator guidance; it does not revive authority.

**VI:** Task đã failed thì phải giữ failure và đối soát phần còn lại. Muốn chạy lại là task/attempt theo contract được cấp quyền mới, không phải vì helper gợi ý restore mà authority tự sống lại.

## Coverage inventory and architectural assessment

| Surface inspected | Existing mechanism and exercised evidence | Assessment |
|---|---|---|
| `storage.py` | Schema-2 writer fences; coarse SQLite/PostgreSQL serialization; scoped lookups; lease/generation/epoch checks; layered reservations; immutable settlement/result binding; accepted candidate retries; complete-frontier review; restore quarantine | Keep the shared authority owner. No newly demonstrated ledger/fencing corruption found. Backend integration was not rerun here. |
| `contracts.py`, `api.py` | Frozen defaults, bounded JSON/body input, explicit bearer tenant/repository grants, review principal binding, scoped artifact membership, per-event cursors | A2 is a narrow validation repair. General identity lifecycle and TLS remain documented operational gaps. |
| `artifacts.py` | Tenant/task namespaces, content hash/size verification, atomic link publication, S3 conditional write/readback | Trusted control-plane root is explicit. S3 deployment and malicious host-level storage replacement were not tested; do not claim hostile filesystem isolation. |
| `engine.py`, `integration.py` | Explicit scripted fixture edits, guarded per-file branches, deterministic conflict detection, exact text-tree manifests, separately reserved verification | A1 is a real defect in an implemented path, independent of acknowledged arbitrary-repository/live-planning gaps. Keep the fixture engine explicitly fixture-specific. |
| `workflows.py` | Stable workflow identity, durable outbox retries, awaited memo reconciliation, stop recheck after activity, bounded history, notifications never execute effects | No new actionable defect found. Injected step still owns effect-boundary fencing; automatic recovery and cleanup dispatch remain separate known work. |
| `recovery.py` | Current-generation check, authoritative dispatch frontier, no implicit owner grant | A3 is a small diagnostic repair. Automatic active-attempt reconciliation is unimplemented and accurately disclosed. |
| `billing.py` | Operator-frozen integer pricing, conservative per-dispatch reservation, exact usage-category accounting | No newly reproduced accounting defect. Price envelope enforcement/evidence remains provider-specific; no paid validation here. |
| `reporting.py` | Committed records, escaped embedded JSON, textContent rendering, source snapshot digest | No executable HTML interpolation found. Evidence limits explicitly separate fixtures and human mastery. |
| `ops/`, `scripts/run_local_checks.py` | Loopback disposable DB, explicit pinned images, fail-closed unconfigured API, scoped test process cleanup, redacted check records, restore runbook | No reason for production deployment or a new operations framework in this audit. Backup restoration/RPO/RTO, hosted lifecycle, S3 and load are acknowledged unmeasured gates. |

**VI:** Chỉ nên refactor nơi làm invariant rõ hơn: preflight contract và receipt validation ở engine, numerical conversion trong timestamp, terminal-state classification trong recovery. Tách RuntimeStore thành nhiều service, đổi locking, thêm enum/framework hoặc mở GPU execution lúc này sẽ thêm rủi ro mà không giải quyết defect đã đo.

The NVIDIA sequence reuses this authority/evidence foundation. NV-S0 CPU observations still do not prove executable provenance, GPU performance or task acceptance. NV-S1–NV-S4 need their already specified source/binary/oracle/environment bindings and hardware retirement design. Fix A1 before treating fixture receipts as a reference pattern for new NVIDIA receipt producers. The local failure-evidence/regression adapter remains the next shared foundation after demonstrated defects are repaired; it should consume accepted immutable evidence without gaining grading or execution authority. No database rewrite is justified by the current findings.

## Measured validation and limits

Executed once:

```sh
.venv/bin/python -m pytest -q tests/test_storage.py tests/test_audit_authority.py tests/test_engine.py tests/test_api.py tests/test_audit_api_artifacts.py tests/test_workflows.py tests/test_review_regressions.py tests/test_audit_ops.py -p no:cacheprovider
```

**Observed:** 82 passed, 2 skipped in 12.94s. Both skips are explicit Temporal local-dev-server opt-ins. Existing tests being green does not falsify A1–A3; the disposable reproductions above exercise missing cases. PostgreSQL tests were inspected but no PostgreSQL, Docker, Temporal server, S3 or GPU integration was launched for this sub-audit. Existing saved backend evidence remains historical evidence. No full-suite count is inferred from this targeted selection. Workspace has no Git repository metadata (`git status` reports “not a git repository”), so source hashes identify audited versions.

| Audited source | SHA-256 |
|---|---|
| service/storage.py | d9ec48f0bb42943bc0f9f039abbb5e4e5afecd5107df17520e81ed0da141c3d4 |
| service/contracts.py | 3a118856412507eb7764991e3f545ffcf614c09ea7d85482bbe0657350f5196d |
| service/artifacts.py | 225455ba1a75f60ff01e4f9f10a3dd7d96127b3fc4dcc30563514718be60571e |
| service/api.py | 5bc9b10e25287f068bfe924dbd38409505ba97dc7cb2a57ffc86161d01eb303c |
| service/engine.py | 86f13fa077d5f36b88c514651c858096b782b2f9c0ef03a27ab15f2262c34e0d |
| service/workflows.py | 2ffd9302bb5a0c865ddb8f39f2fe2d7b8580e85c600760c7e31fae09998f3919 |
| service/recovery.py | 60f233eced6842c488c4da653ab687f28b2dcbd519f40836b5ed409e7965bd2c |
| service/integration.py | 52166832829314f05c5d101cd26298340650a3a0b19ed07f7fcbe68b15052d92 |
| service/billing.py | a3224195aa03fc91ace3c16966154e36592db0e64a6077bbe00c7afdf5131cb0 |
| service/reporting.py | c42df34441d053226613d1b15165491ed584ee671db54560effc97327c74573c |

**VI:** Các hash trên khóa source đã audit trước fix. Sau khi sửa cần record mới cho source mới; không cập nhật lịch sử để làm như tests cũ đã validate code mới. Đây là AI-measured engineering evidence, không ghi mastery của Huy.
