# Stateless Python verifier implementation evidence

Date: 2026-10-10. AI-authored implementation and local mocked checks. Objective: E2/E3 of [the execution specification](../../hackathon/04-execution-specification.md), using [the verifier audit](verifier-contract-audit.md). Existing issue-tracker verification, source fixtures and prior runs remain unchanged. Human H0 mastery remains undemonstrated.

**VI:** Code mới cho controller một cách kiểm function nhỏ trong Docker. Kết quả mock không chứng minh candidate đã chạy thật, model đã sửa được bài, hay container chống được mọi hostile code.

## Owners and the smallest trace

The [recipe validator](../../service/repair_verification.py#L161) freezes supervisor-owned expected data. The [verifier](../../service/repair_verification.py#L337) executes the protected recipe. The caller supplies an exact candidate manifest. `verify` copies its string values before identity calculation or external calls. Each case gets a fresh container seeded from those same bytes plus the fixed `_cam_bridge.py`; argv carries only the selected module/function, args/kwargs and an opaque request ID. The host parses one complete envelope, checks process/response identity, then compares canonical JSON. `true` serializes differently from `1`, including inside nested objects, so Python's `True == 1` cannot turn the former into the latter.

For example, an expectation of integer `1` and a complete response with `value=true` produce `assertion_mismatch`. Exit0 is process evidence, not a verdict. A timeout, malformed envelope or unconfirmed process-group cleanup produces a latched boundary error. Container cleanup is separate evidence: if `close` fails, the report retains the owned ID/nonce when available, marks retirement false, and stops before another case. The parent runner must keep its auxiliary reservation occupied in that state.

**VI:** Có ba quyết định khác nhau: process trả đủ response chưa, response có đúng semantic assertion chưa, và tài nguyên thật đã được retire chưa. PASS cần cả ba; chỉ nhìn exit code hoặc model nói “tests passed” sẽ bỏ mất hai lớp authority.

## Frozen API and supported schema

- `PythonFunctionRecipe.from_dict`, `as_dict`, `public_description`, `grader_digest`.
- `PythonFunctionVerifier(image, *, sandbox_factory=None, recipe=None)`, `environment_digest`, `environment_for(recipe)`, `verify(files, recipe, *, purpose='worker', sandbox_id=None)`.
- Construct with `recipe=recipe` or use `environment_for(recipe)` before freezing the task contract. `environment_digest` without a recipe binds the default limits. The result always binds the supplied recipe's effective limits.

Input top-level keys are exactly `schema`, `recipe_id`, `source_paths`, `module_path`, `functions`, `worker_cases`, `final_cases`, plus optional `limits`. Version is `python-function-recipe-v1`. `limits` may be partial; `as_dict` returns a complete normalized detached copy. Cases have exact fields `id`, `function`, `args`, `kwargs`, `expect`. Expectations contain exactly `value` or `error_type`. Each phase is nonempty; case IDs are unique within that phase; the combined number of cases cannot exceed `max_cases`. IDs are bounded ASCII identifiers. Public function identifiers exclude initial underscores and Python keywords. Candidate paths cannot contain a segment beginning `_cam_`; duplicate, escaping or file/directory-conflicting paths are rejected.

Data supports null, bool, integers with magnitude at most `2**63-1`, strings, lists and string-keyed objects, at depth at most 20. Floating-point values are rejected. Resource `cpus` is finite and positive and normalized to float; other limit fields require exact integers, so booleans cannot be substituted. Expected application exceptions are `ValueError`, `TypeError`, `KeyError`, `IndexError`, `OverflowError`, `RuntimeError`. Unknown exception names produce semantic failure; malformed exception envelopes produce boundary error. No candidate code, import or exception type is executed in the host interpreter.

A recipe loads one explicitly selected `.py` module and top-level export. It does not install dependencies or execute repository test/build/shell commands. Supported functions return JSON data and do not print diagnostics. Multiple source files can be included in the exact manifest, but package/import-graph execution is not a supported recipe feature.

| Effective limit | Default | Supported range |
|---|---:|---:|
| memory_mb |192|32–4096|
| cpus |0.5|greater than 0 through 4|
| pids |32|4–256|
| disk_mb |16|1–128|
| operation_timeout_seconds |5|1–30|
| max_output_bytes |16384|256–65536|
| max_request_bytes |16384|256–65536|
| max_cases |32|1–64 combined across phases|
| max_source_files |50|1–50|
| max_file_bytes |65536|1–262144|
| max_source_bytes |262144|1–262144|
| evaluation_timeout_seconds |600|1–7200|

Full canonical recipe bytes are bounded to 524288. Request bytes are checked at recipe creation, using the actual 32-character request ID shape. Expected envelopes must fit the output bound including bridge ASCII escaping, envelope metadata and the print newline.

**VI:** Default được normalize vào frozen bytes trước khi tính hash. Vì vậy bỏ một limit trong input không tạo “default ngầm” khác với cái container thực sự dùng; đổi bất kỳ limit hiệu lực nào sẽ đổi environment identity.

## Identity, privacy and deadline policy

`grader_digest` binds the complete protected recipe, comparator/exception policy, bridge and actual controller/dependency source digests. `environment_for` binds the resolved immutable image config ID, architecture/Linux OS, full effective limits, bridge/controller/dependency identities, Docker policy and fresh-case isolation. Production construction only inspects an already present pinned image; it never pulls. Injected factories bypass Docker inspection and produce an explicitly different test-only environment identity. Source values, recipes and returned projections are detached.

`public_description` contains public cases and interface/limits, with no `final_cases`. Both worker and final receipts omit raw requests, responses, expected values and exception text; final case names become `private-1`, etc., avoiding leakage through configured private IDs. Observations contain opaque request IDs and request/output digests, bounded reason categories, exit code and elapsed duration. Retirement projects only identity, exact retirement bool and validated hexadecimal owned container ID/creation nonce. Ordinary mismatches yield `fail`; infrastructure/protocol/retirement faults yield `error` and cannot be overwritten by a later pass.

Whole-evaluation admission reserves `operation_timeout_seconds + 420` seconds before each production case. The 420-second allowance conservatively covers the existing Docker backend's bounded 30-second provisioning, nonce recovery, inventory/removal calls, duplicate cleanup paths and launcher cleanup/reaping. If remaining time cannot cover the allowance, no new case is provisioned. The deadline is checked again after case cleanup. Default 600 seconds admits healthy quick cases but deliberately stops provisioning earlier when less than425 seconds remain, preserving cleanup time. A smaller production limit can return a deadline error before creating anything. Mock factories omit this conservative lifecycle reserve and are test-only; they are not certified physical-time environments. Wall time is reported as wall time, never inferred CPU usage or infrastructure dollars.

**VI:** Chạy hết cases không quan trọng hơn việc giữ physical accounting đúng. Budget admission chừa thời gian cleanup trước khi tạo container, thay vì đợi deadline hết rồi giả định process đã biến mất. Runner vẫn phải reserve trước call và chỉ retire slot khi tổng evidence có `retired is True`.

## Measured checks and pending validation

Focused command: `.venv/bin/python -m pytest -q tests/test_repair_verification.py` → **61 passed, 6 skipped** in 0.09s. `.venv/bin/ruff check service/repair_verification.py tests/test_repair_verification.py` → clean. Mocks record snapshots/argv and return scripted envelopes; they never evaluate candidate source in the host.

The [controller controls](../../tests/test_repair_verification.py#L125) cover correct public/final comparison, wrong/unchanged values, booleans versus integers, forged PASS, unknown/extra/wrong-ID/duplicate JSON fields, process timeout/output-limit/nonzero/unretired-group faults, expected exception framing, caller mutation, exact manifests and source bounds, every effective limit's identity, private projection, separate original/cleanup faults, owned identity retention, no subsequent case after uncertainty, and deadline refusal before provisioning.

Six real Docker controls are implemented behind `CAM_TEST_SANDBOX_IMAGE`: correct, unchanged buggy, public-matching wrong control, forged PASS printing, wrong type, and infinite-loop timeout. They were **not run** by this component task; the parent owns the already-authorized local integration run. No image was pulled, paid inference launched or deployment made.

Source digests after focused validation:

- `service/repair_verification.py`: `a0ce818578c99865fb7e8ee5fb8eab1dbd6ca7383d95f3fd8d1608998effa6bd`
- `tests/test_repair_verification.py`: `1128d40ebf48f95b4994b9e81f1f0e90b73355d3ecf2c1c695c37950a88e3a59`

Next: parent integrates auxiliary admission, private recipe storage and exact final receipt identity; run opt-in Docker controls and independent integrated review. No mastery entry or live-model capability result follows from this delivery.

**VI:** Prediction của AI đã được mock quan sát: bool không pass integer, cleanup uncertainty chặn case sau. Phần Docker/model/runner là gate khác, cần evidence riêng; không lấy result cũ của issue-tracker làm result mới.
