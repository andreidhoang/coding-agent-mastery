"""Meaningful trusted-fixture checks; no arbitrary candidate runs on this host."""

import concurrent.futures
import json
import shutil
import subprocess

import pytest

from workloads import (
    inspect_candidate,
    linux_runner_request,
    list_tasks,
    materialize_task,
    tree_digest,
    trusted_control_report,
    validate_assets,
)
from workloads.fixture import Conflict, ImportClient, IssueTracker
from workloads.registry import ROOT


def _csv(prefix="Issue", count=5):
    return "issue_id,title\n" + "".join(f"{i},{prefix} {i}\n" for i in range(count))


def test_frozen_registry_counts_and_honest_provenance():
    evidence = validate_assets()
    assert evidence["tasks"] == 42
    assert len(list_tasks(split="calibration")) == 6
    for tier in ("T1", "T2", "T3"):
        assert len(list_tasks(split="diagnostic", tier=tier)) == 12
    assert len({task.baseline_id for task in list_tasks()}) == 13
    assert len({task.definition_digest for task in list_tasks()}) == 42
    for task in list_tasks():
        definition = task.as_dict()
        assert definition["repository"]["base_commit"] is None
        assert definition["provenance"]["kind"] == "template_variant"
        assert definition["provenance"]["independent_task_claim"] is False
        assert definition["provenance"]["held_out_eligible"] is False
        assert definition["live_run_ready"] is False
        if task.tier == "T3":
            assert len(definition["visible_spec"]["milestones"]) >= 3
            assert len(task.requirements) >= 3


@pytest.mark.parametrize("task", list_tasks(), ids=lambda task: task.task_id)
def test_oracle_controls_for_every_defined_task(task):
    report = trusted_control_report(task)
    assert report["mode"] == "trusted_author_fixture_host_execution"
    assert report["controls_valid"], report
    assert report["controls"]["correct"]["passed"]
    assert not report["controls"]["unchanged"]["passed"]
    assert not report["controls"]["plausible_incorrect"]["passed"]


def test_materialization_excludes_private_assets_and_preserves_baseline(tmp_path):
    task = list_tasks(tier="T3")[0]
    before = validate_assets()
    workspace = materialize_task(task, tmp_path / "workspace")
    assert set(path.name for path in workspace.iterdir()) == {"TASK.json", "client.py", "issue_tracker.py"}
    assert tree_digest(workspace) == task.baseline_digest
    assert "grader_sha256" not in json.loads((workspace / "TASK.json").read_text())
    with pytest.raises(FileExistsError):
        materialize_task(task, workspace)
    (workspace / "issue_tracker.py").write_text("# disposable edit\n")
    assert validate_assets() == before


def test_exact_reference_patch_reconstructs_frozen_expected_tree(tmp_path):
    # Git applies authored text only in disposable dirs; no candidate executes.
    if not shutil.which("git"):
        pytest.skip("patch reconstruction requires Git")
    expected = tree_digest(ROOT / "oracle" / "reference")
    by_base = {task.baseline_id: task for task in list_tasks()}
    for baseline, task in by_base.items():
        workspace = materialize_task(task, tmp_path / baseline)
        result = subprocess.run(
            ["git", "apply", str(task.expected_patch_path)],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert tree_digest(workspace) == expected
        assert expected == task.as_dict()["reference_tree_digest"]
        # A distinct plausible wrong patch must also reconstruct exact bytes.
        wrong_root = materialize_task(task, tmp_path / f"{baseline}_incorrect")
        wrong_patch = ROOT / "oracle" / "patches" / f"{baseline}.incorrect.patch"
        result = subprocess.run(
            ["git", "apply", str(wrong_patch)], cwd=wrong_root, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert tree_digest(wrong_root) == task.as_dict()["incorrect_tree_digest"]


def test_static_admission_does_not_execute_candidate_code(tmp_path):
    task = list_tasks()[0]
    workspace = materialize_task(task, tmp_path / "workspace")
    marker = tmp_path / "MUST_NOT_EXIST"
    payload = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    (workspace / "issue_tracker.py").write_text(payload)
    report = inspect_candidate(task, workspace)
    assert report["status"] == "pending_linux_verification"
    assert report["verified"] is False
    assert not marker.exists()
    request = linux_runner_request(task, workspace, image_digest="sha256:" + "a" * 64)
    assert request["execution_state"] == "not_executed"
    assert request["runner_implementation_status"] == "contract_only_not_implemented"
    assert request["network"] == "disabled"
    assert not marker.exists()


def test_static_admission_rejects_deleted_broken_and_out_of_scope_sources(tmp_path):
    task = list_tasks()[0]
    workspace = materialize_task(task, tmp_path / "workspace")
    client = workspace / "client.py"
    original = client.read_text()
    client.unlink()
    assert inspect_candidate(task, workspace)["status"] == "candidate_invalid"
    client.write_text("def broken(\n")
    assert inspect_candidate(task, workspace)["status"] == "candidate_invalid"
    client.write_text(original)
    (workspace / "private-test.py").write_text("pass\n")
    assert inspect_candidate(task, workspace)["status"] == "candidate_invalid"
    (workspace / "private-test.py").unlink()
    client.unlink()
    client.symlink_to(ROOT / "oracle" / "reference" / "client.py")
    assert inspect_candidate(task, workspace)["status"] == "candidate_invalid"


def test_protected_grader_mutation_is_detected_in_disposable_asset_copy(tmp_path, monkeypatch):
    import workloads.registry as registry

    task = list_tasks()[0]
    workspace = materialize_task(task, tmp_path / "workspace")
    copied_assets = tmp_path / "copied-assets"
    shutil.copytree(ROOT, copied_assets)
    grader = copied_assets / "oracle" / "fixtures" / "acceptance.py"
    grader.write_text("# forged pass attempt\n")
    monkeypatch.setattr(registry, "ROOT", copied_assets)
    monkeypatch.setattr(registry, "REGISTRY_PATH", copied_assets / "manifests" / "tasks.json")
    monkeypatch.setattr(registry, "LOCK_PATH", copied_assets / "manifests" / "assets.lock.json")
    report = registry.inspect_candidate(task, workspace)
    assert report["status"] == "grader_integrity_failed"
    assert report["verified"] is False


@pytest.mark.parametrize("digest", ["latest", "sha256:abc", None, "sha256:" + "g" * 64])
def test_linux_contract_requires_real_digest_shape(tmp_path, digest):
    task = list_tasks()[0]
    workspace = materialize_task(task, tmp_path / "workspace")
    with pytest.raises(ValueError):
        linux_runner_request(task, workspace, image_digest=digest)


def test_resumed_import_cancellation_and_progress_trace(tmp_path):
    database = str(tmp_path / "issues.sqlite")
    tracker = IssueTracker(database)
    job = tracker.submit_import("a", "key", _csv())
    with pytest.raises(RuntimeError):
        tracker.process_batch("a", job, crash_before_commit=True)
    assert tracker.status("a", job)["processed"] == 0
    assert tracker.list_issues("a") == []
    tracker.process_batch("a", job)
    cursor = tracker.progress("a", job, limit=1)["cursor"]
    tracker.close()
    tracker = IssueTracker(database)
    tracker.cancel("a", job)
    tracker.process_batch("a", job)
    assert tracker.status("a", job)["status"] == "cancelled"
    assert len(tracker.list_issues("a")) == 2
    tail = tracker.progress("a", job, cursor, limit=100)
    assert [event["kind"] for event in tail["events"]] == ["batch", "cancelled"]
    assert tracker.progress("a", job, tail["cursor"])["events"] == []
    with pytest.raises(KeyError):
        tracker.status("b", job)
    tracker.close()


def test_duplicate_rows_do_not_change_existing_issue_title():
    tracker = IssueTracker()
    client = ImportClient(tracker, "tenant")
    original = client.import_csv('issue_id,title\n1,"Original, title"\n1,ignored\n', "first")
    assert original == [{"issue_id": "1", "title": "Original, title"}]
    assert client.import_csv("issue_id,title\n1,overwritten?\n", "next") == original
    assert tracker.status("tenant", 1)["processed"] == 2
    with pytest.raises(Conflict):
        client.submit("first", "issue_id,title\n1,changed\n")
    tracker.close()


def test_concurrent_duplicate_submission_and_batches_serialize(tmp_path):
    database = str(tmp_path / "shared.sqlite")
    # Initialize schema before concurrency so this tests effect ownership.
    IssueTracker(database).close()

    def submit():
        tracker = IssueTracker(database)
        try:
            return tracker.submit_import("tenant", "same-key", _csv())
        finally:
            tracker.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: submit(), range(2)))
    assert ids[0] == ids[1]

    def process():
        tracker = IssueTracker(database)
        try:
            return tracker.process_batch("tenant", ids[0], batch_size=2)["processed"]
        finally:
            tracker.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        checkpoints = list(pool.map(lambda _: process(), range(2)))
    assert sorted(checkpoints) == [2, 4]
    tracker = IssueTracker(database)
    tracker.process_batch("tenant", ids[0])
    assert tracker.status("tenant", ids[0])["processed"] == 5
    assert len(tracker.list_issues("tenant")) == 5
    assert tracker.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    tracker.close()


@pytest.mark.parametrize(
    "data",
    [
        "wrong,title\n1,title\n",
        "issue_id,title\n1\n",
        "issue_id,title\n1,title,extra\n",
        "issue_id,title\n1,\n",
    ],
)
def test_bad_csv_has_no_admitted_effect(data):
    tracker = IssueTracker()
    with pytest.raises(ValueError):
        tracker.submit_import("tenant", "key", data)
    assert tracker.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert tracker.list_issues("tenant") == []
    tracker.close()
