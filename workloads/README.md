# Frozen synthetic import workload

This is an AI-authored stdlib Python issue-tracker target and oracle preparation, created on 2026-10-08. It supplies **6 calibration definitions and 36 diagnostic definitions, 12 each in T1/T2/T3**, following the tier counts in capstone/03. All definitions descend from **13 planted-defect templates in one repository family**. Labels distinguish fixture variants; they do not create independent task evidence. No held-out confirmation set exists. T3 has three checkable milestones, but actual hardness, active duration and live-model long-horizon capability are unmeasured.

**VI:** 42 definition không có nghĩa là 42 bài độc lập. Chúng giúp test cơ chế và oracle trong một fixture tổng hợp; chưa đủ để kết luận agent mạnh hơn trên repository thật hoặc nhiều domain.

The corrected target can be imported through `workloads.fixture.IssueTracker` and `ImportClient`. It stores imports, staged CSV rows, issues, checkpoints and events in SQLite. A batch holds one `BEGIN IMMEDIATE` transaction across issue inserts, checkpoint update and event insertion. Duplicate submission uses `(tenant, request_key)` plus a canonical parsed-row digest. Existing issue IDs keep their first title. Cancellation stops later batches, keeps earlier committed rows and never changes a completed job. Cursors bind version, tenant, import and sequence; clients request events strictly after that sequence. `ImportClient.import_csv` keeps synchronous list-of-issues output and finishes all batches before returning.

**VI:** Ví dụ import năm dòng: submit tạo job/checkpoint 0; batch 1 commit hai issue + checkpoint 2 + event; process đóng rồi mở lại vẫn tiếp tục từ dòng 2. Nếu crash được inject trước commit thì cả ba effect rollback. Cancel sau checkpoint 2 giữ hai issue đã commit và không cho batch sau tăng progress. Đây là cơ chế SQLite local, không phải recovery của coding-agent service.

```python
from workloads import list_tasks, materialize_task, inspect_candidate

task = list_tasks(split="diagnostic", tier="T3")[0]
workspace = materialize_task(task, "/absolute/new/disposable/workspace")
result = inspect_candidate(task, workspace)
assert result["verified"] is False  # Static inspection cannot verify behavior.
```

`materialize_task` copies only `issue_tracker.py`, `client.py` and the public `TASK.json` into a new directory. It refuses to overwrite any directory. Grader, expected patches, incorrect controls and asset lock stay outside that root. Baseline identity is SHA256 of canonical sorted `[relative_filename, file_sha256]` pairs, recorded as `sha256-canonical-file-pairs-v1`; no Git commit is invented. The byte hashes, base tree identities, task definition digests, correct and incorrect patch/tree identities and grader identity are pinned by `manifests/assets.lock.json` and `manifests/tasks.json`. `validate_assets` rejects changed protected bytes. Privileged changes to both source and lock remain possible locally; deployment protection requires a separate read-only verifier authority.

`trusted_control_report(task)` explicitly executes only hash-pinned, author-created control code on the host. For every definition it checks unchanged failure, exact reference success and a distinct plausible incorrect fix failure. This is a trusted-fixture validation call, never an arbitrary candidate loader. `oracle/patches/<baseline>.patch` and `<baseline>.incorrect.patch` reconstruct the corresponding exact control trees. The authoring entry point `python -m workloads.freeze_catalog` refuses to overwrite an existing lock; future revisions require a deliberately new registry version.

`inspect_candidate` bounds source bytes and directory entries, rejects missing files, extra paths, symlinks and syntax errors, and parses/compiles without executing candidate code. Valid syntax receives `pending_linux_verification`, never a passing receipt. An environment-breaking candidate receives a static admission error; static checks do not detect every runtime failure. They also cannot establish hostile-code containment.

**VI:** `compile` tạo code object nhưng không chạy top-level code. Test đưa source có side effect ghi file vào candidate và xác nhận file đó không xuất hiện. Result vẫn là pending vì syntax đúng không chứng minh chức năng đúng.

`linux_runner_request` prepares a data-only contract with exact task/tree/grader identities, a caller-selected image digest, architecture, fixed positive CPU/RAM/process/disk/output/time limits, disabled network and no credentials. It launches nothing and this workload module does not implement the external supervisor or select a deployment image. Integrated execution-adapter evidence is maintained separately under `service/`. A runner must keep candidate code in a separate isolated interpreter/process, use a trusted external grading/protocol adapter, and authenticate receipts from the supervisor. Merely mounting a grader file read-only while importing hostile candidate code into the grader interpreter does not protect grading authority. The local class-based `acceptance.py` controls are not that protocol adapter.

The full live-run manifest still needs real repository/task sampling, Linux image and enforcement evidence, provider/model/settings, spending ceilings, human review and a frozen protocol. Calibration/development variants share lineage and must not cross into a purported held-out set. Independent reproduction, human mastery and production readiness remain pending.

The authored `skills/verified-repair-guide/` fixture is separate from the 42-task population and its 82 locked assets. [Capture](../service/skills.py) snapshots its three text assets; broker-v1 provides a detached receipt trace. [Accepted disclosure step4](../research/skills-disclosure-spec-2026-10-11.md) uses the same package for an actual native mock HTTP trace: empty state → load → later accepted primary → exact two resource chunks after disposable-origin mutation. [Verification](../research/skills-disclosure-verification-2026-10-11.json) owns that evidence. It adds no workload, script, installation or capability. Typed skills recovery remains step5; the preserved October10 candidate excludes all these later additions.

Run local checks with `python -m pytest tests/test_workloads.py -q`. These checks execute only trusted fixtures and reconstruct patches in disposable directories. They preserve the historical lab, reference sources and prior runs.
