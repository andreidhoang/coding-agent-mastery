# Supported Python repository verifier contract audit

Date: 2026-10-10. Status: AI-authored source audit and proposed implementation contract. This report makes no new live-model, Docker-execution, production-isolation or human-mastery claim. Only local Docker inventory/image inspection was performed; no image was pulled, container started, deployment made or paid service called. Existing source, fixtures and prior runs are preserved. The parent implementation task owns source changes and subsequent validation.

## Decision for the next bounded implementation

Add a separately named reusable **stateless Python function recipe** alongside the existing issue-tracker verifier. It accepts a frozen UTF-8 source manifest, an explicitly selected Python module/function interface, and bounded JSON inputs. A trusted host controller compares returned data with protected expected data. Public worker cases and private final cases are separate inputs and projections. Do not remove the issue-tracker verifier's exact-file guard or treat arbitrary candidate-controlled pytest exit status as independent verification.

**VI:** Một recipe mô tả cách gọi API nhỏ và cách so kết quả. Model chỉ sửa source được cho phép; controller giữ expected output và quyền ghi receipt. Ta mở rộng loại repository được hỗ trợ bằng contract mới, không đổi tên fixture thành general repository agent.

Frozen minimal API agreed with the parent implementation task (`service/repair_verification.py`):

```python
PythonFunctionRecipe.from_dict(trusted_config) -> PythonFunctionRecipe
recipe.as_dict() -> dict                                 # trusted full frozen schema
recipe.public_description() -> dict                       # worker-safe projection only
recipe.grader_digest -> str                               # protected checks + controller semantics
PythonFunctionVerifier(image, *, sandbox_factory=None)
verifier.environment_digest -> str
verifier.verify(files, recipe, *, purpose="worker", sandbox_id=None) -> CheckResult
# purpose is exactly worker | final; selected only by trusted controller
```

`files` is copied before hashing or external calls; values must be immutable strings. `purpose` is selected by the controller, never a tool argument; `phase` in the report below denotes that same field. `run_tests` remains argument-free and always selects `worker`. The final path accepts the immutable integrated candidate dictionary. Production construction uses the real Docker factory; injected mocks are test-only and cannot emit a production environment identity. The verifier should not need the model, reference patch or known-correct implementation.

**VI:** Worker callback phải đọc snapshot hiện tại ngay lúc được gọi. Nếu closure giữ base ban đầu, agent sửa đúng vẫn nhận test cũ; nếu callback dùng private phase, agent lại có một đường hỏi oracle ngoài contract.

## Evidence inspected and reusable mechanisms

| Inspected source | Established behavior | New caller obligation |
|---|---|---|
| [tree identity](../../service/execution.py#L36) | Canonical supported text-tree digest | Freeze copied input before computing digest; reject unexpected/missing paths |
| [workspace snapshot](../../service/execution.py#L103) | Reads every regular file below root, rejects symlinks and oversize trees | Materialize only public allowed inputs; keep protected recipe/artifacts outside this root |
| [worker tests](../../service/harness.py#L22) | Broker calls configured callback with a current workspace snapshot; durable tool dispatch precedes effect | Configure fixed public callback; reserve the actual test environment and retain uncertainty |
| [bounded launcher](../../service/execution.py#L149) | Wall timeout/output limit; owned process-group TERM/KILL cleanup; explicit retirement field | Validate completion reason and launcher retirement, not just exit code |
| [Docker sandbox](../../service/execution.py#L248) | Local immutable image, network none, no host mounts, read-only root, nonroot user, dropped capabilities, bounded writable tmpfs | Freeze all effective limits; create fresh isolated candidate environment per independent case |
| [container creation](../../service/execution.py#L329) | Source copy, unique creation nonce, immutable container-ID ownership | Persist reservation before provisioning; keep provisioning ambiguity visible |
| [container execution/retirement](../../service/execution.py#L423) | Fixed workdir, empty environment, bounded execution; removal confirmed by inventory | Treat failed/uncertain close as unresolved, keep slot occupied |
| [existing Linux verifier](../../service/verification.py#L117) | Host-owned oracle through limited issue-tracker RPC, copied tree identity, latched boundary faults | Preserve this guard and design pattern; create a separate recipe implementation |
| [strict JSON](../../service/protocol.py#L18) | Rejects duplicate keys, nonfinite values, exponent overflow, trailing data and excessive depth/size | Validate exact envelope shape and field types in addition to parse validity |
| [auxiliary admission](../../service/storage.py#L1527) | Reserved environments count toward service/tenant capacity; one active auxiliary role per task | Reserve before every new evaluation; duplicate reservation is reconciliation, not rerun permission |
| [retirement authority](../../service/storage.py#L991) | Trusted caller can retire from nonempty evidence | Caller must require independently confirmed `retired is True`; an exception is not retirement evidence |
| [verification identity](../../service/storage.py#L1224) | Current head/generation and frozen tree/grader/environment checked before receipt | Compare returned verifier identities with expected identities before writing receipt |

**VI:** Database kiểm identity nhưng không tự chạy test hay xác thực mọi nội dung evidence. Caller vẫn là trusted boundary: nếu tự truyền `outcome='pass'` từ text candidate thì invariant ở storage không cứu được.

Existing regressions inspected include caller-mutation identity, malformed response versus expected application exception, latched faults even if a grader catches all exceptions, immutable-ID cleanup and uncertain provisioning in [audit tests](../../tests/test_audit_execution.py#L48). These are existing tests read during this audit, not newly executed results.

## Minimal schema and supported repository boundary

The trusted recipe schema should use exact keys and a version. Reject unknown keys rather than ignoring an accidentally misspelled limit. Proposed fields:

```text
schema: "python-function-recipe-v1"
recipe_id: bounded stable identifier
source_paths: nonempty exact canonical relative UTF-8 file manifest
module_path: one source_paths entry ending .py
functions: nonempty allowlist of public Python identifiers
worker_cases: nonempty bounded list[Case]
final_cases: nonempty bounded list[Case]
limits: frozen Limits

Case:
  id: unique bounded identifier within phase
  function: one allowlisted function
  args: JSON list
  kwargs: JSON object with string keys
  expect: exactly one of {value: JSON value} or {error_type: allowed exception name}

Limits:
  memory_mb, cpus, pids, disk_mb
  operation_timeout_seconds
  max_output_bytes, max_request_bytes, max_cases
  max_source_files, max_file_bytes, max_source_bytes
```

All numbers must have exact intended types, finite values and supported positive ranges; `True` must not count as integer one. Nested input data and expectations must survive strict JSON validation and be deep-frozen/canonicalized. Require at least one meaningful assertion per phase, unique case IDs, declared functions, valid module path, bounded serialized request bytes and bounded total case count. For an initial implementation use integers, strings, booleans, null, lists and string-keyed objects; either reject floats or explicitly choose exact canonical numeric semantics. Do not silently use Python `==`, where `True == 1`.

**VI:** Schema validation chặn recipe rỗng vẫn `all([])==True`, và chặn response trả boolean thay cho số nguyên nhưng vô tình pass. Đây là lỗi ở grader, không phải ở model.

A suitable authored demonstration is a small `duration.py` module with pure `parse_duration(text)` and `format_duration(seconds)` functions. Public cases teach ordinary parsing/formatting; protected cases distinguish malformed fields, minute/second bounds, zero, large hours, round-trips and an intentionally wrong control. Select exact semantics before implementation: accepted grammar, whitespace policy, integer range and invalid-input exception. This is a suggested task family, not an implemented fixture or a claim of held-out performance.

Support a single explicitly loaded module initially, or a precisely declared import graph with its own tests. Avoid package installation, setup scripts, repository-defined test commands, shell commands, arbitrary import names, arbitrary attributes or loading candidate code in the host interpreter. Reject unsupported recipes instead of guessing an execution command. Standard-library-only code is sufficient for this slice. The worker may see all public source files and issue text; none contains the protected cases, reference implementation or patch.

**VI:** “Reusable” nghĩa thay module/function/cases trong schema được hỗ trợ. Nó chưa có nghĩa mọi Python project có dependency, build hook, package layout hoặc integration service đều chạy được.

## RPC and trust contract

Use a fixed trusted bridge passed as `python -I -c BRIDGE_SOURCE REQUEST_JSON` inside Docker, or a reserved `_cam_bridge.py` file copied by the controller. For the file form, reject every candidate path in the reserved bridge namespace and include bridge content in environment identity; it must contain no expectations. The bridge loads only the declared module using its absolute `/workspace/...` path, resolves only the declared top-level function, calls it with JSON args/kwargs, and writes one JSON object. No expected output, hidden case list, grader source or host path is present in argv, source files, container environment or image. Candidate code can inspect its invocation; sending only the current operation input is part of the black-box interface, not disclosure of its expected result.

```json
{"schema":1,"request_id":"opaque-case-operation-id","module":"duration.py","function":"parse_duration","args":["1:02:03"],"kwargs":{}}
```

Exact success shape: `{"schema":1,"request_id":"...","ok":true,"value":3723}`. Exact application-error shape: `{"schema":1,"request_id":"...","ok":false,"error_type":"ValueError","message":"bounded text"}`. The host must validate exact field set, exact bool type, echoed request ID and bounded field lengths. Unknown application exception names fail the semantic case unless a fixed small allowlist explicitly defines them; do not dynamically import/instantiate an exception class named by candidate data. Expected exceptions are matched as data only after transport/schema checks succeed.

**VI:** Candidate có thể fake một envelope hợp lệ như mọi chương trình có thể trả một giá trị. Điều ta đo là input/output behavior có đúng không, không chứng minh một exception thực sự được raise ở dòng code nào. Token/request ID giúp nối observation; nó không biến candidate response thành trusted receipt.

Consume the entire bounded output through strict JSON parsing. Extra `PASS`, multiple JSON documents, a candidate-authored `passed` field, absent required fields, wrong request IDs and duplicate keys are boundary failures. Treat nonzero exit, timeout, output truncation, transport exception, launcher process-group retirement failure and malformed response as a latched fault. A later valid response or expected `ValueError` cannot clear it. Never call candidate result data as Python code. Host comparison produces per-case booleans and the overall verdict.

Separate stdout/stderr is optional future work; existing `bounded_process` merges them. Under this minimal protocol, diagnostic output mixed with the envelope fails framing. Document that supported functions must not print diagnostics. Avoid a “last JSON line wins” parser that permits forged/multiple replies.

**VI:** Timeout mà parse được prefix `{"ok":false,...}` vẫn là timeout. Nếu cho expected-exception handler nuốt lỗi transport, một chương trình cố ý phá protocol có thể đậu case invalid-input.

## Exact candidate, case isolation and identities

Capture `frozen_files = dict(files)` and `tree_digest(frozen_files)` before provisioning. Because source values are strings, this copies the mutable mapping boundary. Validate exact path set and size bounds, then use only the copy. For worker tests, the broker's current snapshot is the input; for final checks, use the immutable integrated artifact, not a mutable worker directory. Include unchanged/read-only source files in the tree identity and sandbox snapshot even when only a subset is editable.

For each independent stateless assertion start a fresh `DockerSandbox` from the same frozen files and close it before the next. Existing `/workspace` is writable tmpfs: sharing it allows candidate self-modification, persistent files and background processes to contaminate later cases. A fresh container per case is the smallest strong default without adding a new read-only source mechanism. A sequence-based stateful recipe is a distinct future version with explicitly different semantics.

**VI:** Digest xác định bytes lúc bắt đầu chạy. Candidate vẫn có thể tự sửa bộ nhớ/file trong chính lần chạy đó; đó là behavior của chương trình. Vấn đề cần tránh là case sau vô tình khởi đầu từ bytes đã bị case trước sửa.

Freeze three different identities:

1. `recipe/grader_digest`: canonical full trusted recipe including public/protected cases, comparator/exception policy and actual controller/bridge implementation version or content digest.
2. `environment_digest`: resolved immutable Linux image config ID, architecture, OS, bridge identity, resource and request/output/source/case limits, timeout policy, workdir, uid/gid, network/mount/capability/environment policy and case-isolation mode. A mutable tag or just the original image string is insufficient.
3. `tree_digest`: exact supported text manifest copied to the sandbox. The runner additionally binds task contract, base Git commit/base tree, generation/current head and candidate ID through existing store contracts.

Copy/deep-freeze recipe state as well as source files. Mutating a caller-owned case list after digest creation must not change the checks without changing identity. Recompute/assert identity at the use boundary or store immutable canonical bytes. Worker phase identity must be distinct from final evidence; public test success cannot substitute for a final pass.

**VI:** Một hash chỉ có ích khi thứ thực sự chạy vẫn đúng là thứ được hash. Cùng image nhưng đổi timeout hoặc expected values là điều kiện thử khác và cần identity khác.

## Physical accounting and failure lifecycle

The worker patch grant already occupies its own slot. Each actual Docker evaluation needs separate physical admission before creation. Reuse `reserve_environment(..., kind='verifier', reservation_id=...)` for serial public tests and final verification, with purpose/dispatch identity in durable evidence. The current storage API supports only `verifier` and `integrator` auxiliary kinds. Do not invent an unaccounted worker-test container, and do not retire the patch grant when retiring its test container. Capacity configuration must allow the patch grant plus one auxiliary environment.

One evaluation reservation can cover serial fresh case containers when **at most one is live** and every prior container's retirement is confirmed before provisioning the next. Derive distinct bounded Docker identities from reservation ID and case ordinal. Store every owned immutable container ID/nonce and retirement observation. A failed close aborts evaluation and retains the reservation; it must never advance to the next case or attempt final verification with that uncertain slot.

**VI:** Reservation là chỗ cho tài nguyên thật, không phải số task logic. Agent workspace và Docker test có thể tồn tại cùng lúc nên cần hai slot; cancel quyền làm việc không tự xóa container.

The controller must preserve both the original execution fault and cleanup fault, instead of allowing a `finally` exception to erase the first. Return or persist a bounded error record with `passed=false`, `outcome=error`, fault category, known container identity and cleanup status. Record ordinary wrong outputs as `outcome=fail`, keeping infrastructure/boundary faults distinguishable. `passed=true` requires all required assertions, no latched faults and confirmed physical cleanup.

Retire storage only when the collected trusted retirement observation has `retired is True` for every provisioned case. A process exit, timeout, exception, absent local handle, failed inventory command or same-name container is not proof. Keep nonce/immutable-ID authority from `DockerSandbox`; never remove a container based solely on display name. A duplicate reservation with no durable completed result requires reconciliation, not automatic replay.

**VI:** Có thể output đã đúng nhưng container removal chưa rõ. Khi đó giữ evidence output và uncertainty; không đổi thành success sạch hay thả slot để chạy thêm.

Per-operation timeout does not bound the entire evaluation: image inspect/create/start/copy/close each have launcher bounds and multiple cases multiply work. Freeze a bounded case count and overall evaluation deadline/check budget, check remaining allowance before starting another case, and report actual elapsed time separately. Existing container CPU setting is a rate cap, not measured CPU usage or a dollar charge. Do not label wall time as CPU-seconds or infer infrastructure cost from it. Source-side termination remains distinct from DB-time deadline eligibility at result commit.

## Proposed result and privacy projection

```text
CheckResult:
  schema, recipe_id, phase, mode
  passed: bool
  outcome: pass | fail | error
  tree_digest, grader_digest, environment_digest
  cases: list[{id, passed, category}]
  observations: list[{opaque request ID/digest, exit_code, reason,
                     duration_seconds, output_digest, bounded fault category}]
  boundary_failures: list[bounded structured fault]
  retirement: {retired: bool, instances: list[owned identity + evidence]}
  limits, elapsed_seconds, limitations
```

Public worker feedback may include public expected/actual values and bounded diagnostics useful for repair. Final evidence given to the worker or public UI should include aggregate/per-criterion outcomes and identities without raw private requests, expected values or candidate-echoed hidden inputs. Keep raw final response artifacts in a protected supervisor-only area if retained; the current store artifact authorization is task-scoped, so do not assume linking a raw private response artifact into ordinary task evidence hides it from the task reader. Hashes and opaque case IDs suffice for the minimal public receipt.

**VI:** Không truyền hidden expected values cho container vẫn chưa đủ nếu UI hoặc tool response lại mở toàn bộ raw grader evidence cho agent. Cần kiểm tra cả projection sau khi chạy, nhất là candidate có thể echo input vào output.

## Distinguishing validation matrix

These are AI-authored predictions for the implementation work, not completed experiments or Huy's predictions.

| Test/control | Required discriminating observation |
|---|---|
| Authored correct candidate, real opt-in Docker | Required public/final cases pass with matching exact tree and confirmed cleanup |
| Unchanged buggy baseline | At least one predeclared public or final behavior fails; cannot publish review |
| Deliberately wrong candidate matching visible cases | Protected final case fails |
| Candidate prints `PASS` / `{"passed":true}` then exit0 | Boundary error, never pass |
| Complete but wrong data envelope | Host comparison fails independent of exit0 |
| Bool response for integer expectation | Fails type-aware equality |
| Expected ValueError case with malformed/oversize/timeout output | Latched boundary error, never exception-case pass |
| Candidate writes source or leaves child | Next independent case starts from original snapshot in fresh container |
| Caller mutates file dictionary or nested recipe during start | Executed bytes/checks retain frozen identity |
| Worker edits file then runs tests | Callback receives current digest, not base snapshot |
| Worker/source attempts to read protected recipe | Recipe absent from materialized manifest and model projection |
| Cleanup inventory fails / unknown creation | Reservation retained; no next case or review pass |
| Repeated dispatch/reservation after crash | Durable known result replayed, or unresolved state retained; no blind rerun |
| Final receipt for tree A after head changed to B | Existing store rejects stale/mismatched verification |
| No cases / unknown module/function / excessive request | Reject before candidate execution |

Mock tests should inject a sandbox implementing only `start(files)`, `run(argv,max_output=...)`, and `close()` with fixed scripted responses and a declared test environment identity. It records snapshots/arguments, deliberately mutates caller inputs, and simulates all fault/cleanup paths. It must never import/evaluate/execute arbitrary candidate Python in the host process. Mock pass establishes controller/protocol behavior only; it is not a candidate-execution or isolation result. Test a healthy authored program and adversarial programs separately through the opt-in real Docker path.

**VI:** Mock kiểm controller làm đúng khi nhận response X. Docker test kiểm candidate thật tạo response gì trong môi trường thật. Hai lớp evidence khác nhau, cần báo riêng.

## Local runtime observation and handoff

Read-only Docker inventory succeeded during this audit. The already present Python image `sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9` inspects as `arm64 linux`, no image entrypoint, default command `["python3"]`. This is a candidate for opt-in validation; its presence does not prove the new bridge or recipe runs correctly. Use the exact immutable ID and record architecture. No runtime validation was launched by this audit.

Next engineering step: implement the separate strict recipe/controller with injectable mock backend, then connect the existing current-snapshot worker callback and exact integrated final path using durable auxiliary reservations. Execute the discriminating tests, record real-versus-mock evidence separately, and review worker/final projections before any live model run. Authenticated model/catalog, authoritative price/bounds, explicit spending ceiling and selected target task remain parent-runner concerns. Human H0 mastery remains undemonstrated.

**VI:** Kết quả audit là contract có thể implement và test, không phải sản phẩm đã chạy live. Bước tiếp theo phải giữ nguyên sự khác nhau giữa proposed, source-implemented và measured.
