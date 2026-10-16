"""Frozen R1-R3 controls: evidence validation and data-only candidate intake."""

import os
import socket
import tempfile
from pathlib import Path

import pytest

import evals.analysis as analysis
from evals.fixtures import accepted_fixture, demo_manifest
from workloads import inspect_candidate, materialize_task, tree_digest
from workloads.registry import MAX_CANDIDATE_BYTES


IDENTITY_FIELDS = (
    "task_id",
    "base_commit",
    "candidate_digest",
    "verified_digest",
    "grader_digest",
    "eligibility_receipt",
    "review_receipt",
)
FACT_FIELDS = (
    "submitted_at",
    "verified_at",
    "eligibility_decision_at",
    "eligibility_committed_at",
    "review_at",
    "withdrawn_at",
)


@pytest.fixture
def assigned():
    frozen = demo_manifest(tasks_count=1, trials=1, arms=("bare", "coordinated_n2"))
    return frozen, frozen.read()["planned_rows"][0]


@pytest.mark.parametrize("field", IDENTITY_FIELDS)
@pytest.mark.parametrize("identity", ["", " \t\n", {}, [], 0, True])
def test_invalid_acceptance_identity_retains_assignment_and_spend(assigned, field, identity):
    frozen, row = assigned
    outcome = accepted_fixture(
        row, **{field: identity}, settled_usd=3, reserved_usd=2, unknown_usd=4, input_tokens=7
    )
    report = analysis.analyze(frozen, [outcome], bootstrap=1)
    assert report["counts"] == {
        "assigned": 2,
        "started": 1,
        "completed": 1,
        "accepted": 0,
        "reasons": {"accepted_claim_without_eligibility": 1, "missing": 1},
    }
    assert report["accounting"]["settled_usd"] == 3
    assert report["accounting"]["total_exposure_usd"] == 9
    assert report["accounting"]["input_tokens"] == 7
    assert row["row_id"] in report["included_row_ids"]


@pytest.mark.parametrize("identity", ["", " \t\n", {}, [], 0, True])
def test_equal_invalid_candidate_identities_cannot_score_accepted(assigned, identity):
    frozen, row = assigned
    report = analysis.analyze(
        frozen, [accepted_fixture(row, candidate_digest=identity, verified_digest=identity)], bootstrap=1
    )
    assert report["counts"]["accepted"] == 0
    assert report["counts"]["reasons"]["accepted_claim_without_eligibility"] == 1


@pytest.mark.parametrize(
    "candidate,verified,score",
    [("synthetic-tree", "synthetic-tree", 1), ("synthetic-tree", "different-tree", 0)],
)
def test_synthetic_identity_equality_remains_supported(assigned, candidate, verified, score):
    frozen, row = assigned
    report = analysis.analyze(
        frozen, [accepted_fixture(row, candidate_digest=candidate, verified_digest=verified)], bootstrap=1
    )
    assert report["counts"]["accepted"] == score
    assert report["counts"]["assigned"] == 2
    assert report["accounting"]["settled_usd"] == 1


@pytest.mark.parametrize("field", FACT_FIELDS)
@pytest.mark.parametrize("status", ["accepted", "candidate_failed", "effect_unknown"])
@pytest.mark.parametrize("recorded_at", [120, 201])
def test_future_facts_reject_before_scoring_or_cutoff_selection(
    assigned, monkeypatch, field, status, recorded_at
):
    frozen, row = assigned
    outcome = accepted_fixture(row, status=status, recorded_at=recorded_at, **{field: recorded_at + 1})

    def must_not_score(*args):
        pytest.fail("invalid chronology reached scoring")

    monkeypatch.setattr(analysis, "accepted", must_not_score)
    with pytest.raises(ValueError, match=field):
        analysis.analyze(frozen, [outcome], bootstrap=1)


def test_reported_acceptance_cannot_precede_its_facts(assigned):
    frozen, row = assigned
    with pytest.raises(ValueError):
        analysis.analyze(frozen, [accepted_fixture(row, recorded_at=1)], bootstrap=1)
    assert analysis.analyze(frozen, [accepted_fixture(row, recorded_at=120)], bootstrap=1)["counts"][
        "accepted"
    ] == 1


@pytest.mark.parametrize("field", FACT_FIELDS)
def test_facts_at_recording_time_are_valid(assigned, field):
    frozen, row = assigned
    outcome = {"row_id": row["row_id"], "recorded_at": 50, "status": "candidate_failed", field: 50}
    report = analysis.analyze(frozen, [outcome], bootstrap=1)
    assert report["counts"]["accepted"] == 0
    assert report["counts"]["reasons"]["candidate_failed"] == 1


def test_valid_late_revision_does_not_backdate_cutoff_or_erase_consumption(assigned):
    frozen, row = assigned
    initial = {
        "row_id": row["row_id"],
        "result_id": "first",
        "recorded_at": 50,
        "status": "effect_unknown",
        "submitted_at": 0,
        "settled_usd": 2,
        "unknown_usd": 7,
        "input_tokens": 3,
    }
    late = accepted_fixture(
        row, result_id="late", supersedes_id="first", recorded_at=201, settled_usd=5, input_tokens=8
    )
    before = analysis.analyze(frozen, [initial], bootstrap=1)
    after = analysis.analyze(frozen, [initial, late], bootstrap=1)
    assert after["counts"] == before["counts"]
    assert after["accounting"] == before["accounting"]
    assert after["raw_result_digest"] != before["raw_result_digest"]
    assert after["counts"]["assigned"] == 2
    assert after["counts"]["accepted"] == 0
    assert after["accounting"]["total_exposure_usd"] == 9
    timely = dict(late, recorded_at=150)
    timely_report = analysis.analyze(frozen, [initial, timely], bootstrap=1)
    assert timely_report["counts"]["accepted"] == 1
    assert timely_report["accounting"]["settled_usd"] == 5
    assert timely_report["accounting"]["input_tokens"] == 8
    decreasing = dict(timely, input_tokens=2)
    with pytest.raises(ValueError, match="cumulative"):
        analysis.analyze(frozen, [initial, decreasing], bootstrap=1)


@pytest.mark.parametrize("kind", ["fifo", "socket"])
@pytest.mark.parametrize("name", ["undeclared_entry", "client.py", "TASK.json"])
def test_nonregular_entries_are_rejected_before_candidate_reads(monkeypatch, kind, name):
    if kind == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable on this platform")
    if kind == "socket" and not hasattr(socket, "AF_UNIX"):
        pytest.skip("Unix socket unavailable on this platform")
    # Keep the Unix socket path within the OS path limit, independent of pytest names.
    with tempfile.TemporaryDirectory(prefix="r3-", dir="/tmp") as temporary:
        root = materialize_task("calibration-01", Path(temporary) / "candidate")
        entry = root / name
        if entry.exists():
            entry.unlink()
        listener = None
        if kind == "fifo":
            os.mkfifo(entry)
        else:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(entry))
        candidate_reads = []

        def tracked_read(method):
            def read(path, *args, **kwargs):
                if root in path.parents:
                    candidate_reads.append(path)
                    assert path != entry, "nonregular candidate entry was opened"
                return method(path, *args, **kwargs)

            return read

        monkeypatch.setattr(Path, "read_text", tracked_read(Path.read_text))
        monkeypatch.setattr(Path, "read_bytes", tracked_read(Path.read_bytes))
        try:
            report = inspect_candidate("calibration-01", root)
        finally:
            if listener is not None:
                listener.close()
        assert report["status"] == "candidate_invalid"
        assert report["verified"] is False
        assert report["candidate_digest"] is None
        assert any("nonregular" in problem and name in problem for problem in report["problems"])
        assert candidate_reads == []


def test_regular_candidate_stays_pending_independent_verification(tmp_path):
    root = materialize_task("calibration-01", tmp_path / "candidate")
    report = inspect_candidate("calibration-01", root)
    assert report["status"] == "pending_linux_verification"
    assert report["verified"] is False
    assert report["candidate_digest"] == tree_digest(root)
    assert report["problems"] == []


@pytest.mark.parametrize("kind", ["directory", "symlink", "undeclared", "bytes", "entries"])
def test_existing_candidate_guards_remain_enforced(tmp_path, kind):
    root = materialize_task("calibration-01", tmp_path / "candidate")
    if kind == "directory":
        (root / "directory").mkdir()
    elif kind == "symlink":
        (root / "alias").symlink_to(root / "client.py")
    elif kind == "undeclared":
        (root / "extra.py").write_text("pass\n")
    elif kind == "bytes":
        (root / "client.py").write_bytes(b"#" * (MAX_CANDIDATE_BYTES + 1))
    else:
        for index in range(128):
            (root / f"extra-{index}").touch()
    report = inspect_candidate("calibration-01", root)
    assert report["status"] == "candidate_invalid"
    assert report["verified"] is False
    assert report["candidate_digest"] is None
