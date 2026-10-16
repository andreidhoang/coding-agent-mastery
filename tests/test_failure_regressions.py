"""Closed data predicates and immutable proposals are separate from runtime acceptance."""

import copy
import json

import pytest

from failure_adapter_helpers import (
    capture,
    extract,
    failed_verification,
    failure_store,
    fingerprint,
    fixtures_for,
    unknown_dispatch,
)
from service.artifacts import canonical_bytes, digest_bytes

assert failure_store


def proposal_inputs(store, kind):
    if kind == "failed_verification":
        task, verification, _, _ = failed_verification(store)
        subject = verification["verification_id"]
    else:
        task, subject = unknown_dispatch(store)
    evidence = extract(store, task, kind, subject)
    predicate, controls = fixtures_for(evidence)
    ref = store.artifact_store.put_json("tenant", task["task_id"], controls)
    return task, evidence, predicate, controls, ref


def freeze(store, evidence, predicate, ref, **kwargs):
    from evals.regressions import freeze_regression_case

    return freeze_regression_case(
        evidence,
        fixture_ref=ref,
        predicate_id=predicate,
        source_hashes={"adapter-source": "a" * 64},
        artifact_reader=store.artifact_store.get,
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["failed_verification", "unknown_dispatch"])
def test_both_predicates_good_true_bad_false_pending_case_and_ai_review(failure_store, kind):
    from evals.regressions import evaluate_regression_fixture, record_regression_review

    task, evidence, predicate, controls, ref = proposal_inputs(failure_store, kind)
    before = fingerprint(failure_store)
    assert evaluate_regression_fixture(predicate, controls["known_good"], evidence=evidence) is True
    assert evaluate_regression_fixture(predicate, controls["known_bad"], evidence=evidence) is False
    case = freeze(failure_store, evidence, predicate, ref, fix_revision="declared-unverified-revision")
    assert case.verify()["review_state"] == "pending"
    assert case.verify()["control_results"] == {"known_good": True, "known_bad": False}
    assert case.verify()["lineage"] == evidence.verify()["lineage"]
    assert (
        freeze(failure_store, evidence, predicate, ref, fix_revision="declared-unverified-revision") == case
    )
    review_args = {
        "reviewer_id": "AI-test-reviewer",
        "reviewer_kind": "ai",
        "disposition": "approved",
        "reasons": ["data invariants inspected; no candidate acceptance"],
        "reviewed_at": 10,
    }
    review = record_regression_review(case, **review_args)
    assert review.verify()["reviewer_kind"] == "ai"
    assert review.verify()["authority"] == "caller_declared_review_only"
    assert review.verify()["case_digest"] == case.digest
    assert record_regression_review(case, **review_args) == review
    assert record_regression_review(case, **{**review_args, "reviewed_at": 11}).digest != review.digest
    case.read()["lineage"]["source_case_id"] = "mutation"
    review.read()["disposition"] = "rejected"
    assert case.verify()["review_state"] == "pending"
    assert review.verify()["disposition"] == "approved"
    assert fingerprint(failure_store) == before
    assert capture(failure_store, task)["snapshot"]["reviews"] == []


@pytest.mark.parametrize("kind", ["failed_verification", "unknown_dispatch"])
@pytest.mark.parametrize(
    "defect",
    [
        "unchanged",
        "reversed",
        "wrong_good",
        "evidence_digest",
        "predicate_id",
        "extra",
        "executable",
        "wrong_scope",
        "bad_size",
        "oversized",
    ],
)
def test_invalid_control_pair_cannot_create_case(failure_store, kind, defect):
    _, evidence, predicate, controls, ref = proposal_inputs(failure_store, kind)
    controls = copy.deepcopy(controls)
    if defect == "unchanged":
        controls["known_bad"] = copy.deepcopy(controls["known_good"])
    elif defect == "reversed":
        controls["known_bad"], controls["known_good"] = controls["known_good"], controls["known_bad"]
    elif defect == "wrong_good":
        key = "grader_digest" if kind == "failed_verification" else "bound_units"
        controls["known_good"][key] = "f" * 64 if kind == "failed_verification" else 11
    elif defect == "evidence_digest":
        controls["evidence_digest"] = "f" * 64
    elif defect == "predicate_id":
        controls["predicate_id"] = "arbitrary.import.execute"
    elif defect == "extra":
        controls["accepted"] = True
    elif defect == "executable":
        controls["known_good"]["expression"] = "__import__('os').system('touch marker')"
    elif defect == "oversized":
        controls["padding"] = "x" * 65536
    ref = failure_store.artifact_store.put_json(ref["tenant_id"], ref["task_id"], controls)
    if defect == "wrong_scope":
        ref = {**ref, "tenant_id": "other"}
    elif defect == "bad_size":
        ref = {**ref, "size": ref["size"] + 1}
    with pytest.raises(ValueError):
        freeze(failure_store, evidence, predicate, ref)


@pytest.mark.parametrize("kind", ["failed_verification", "unknown_dispatch"])
@pytest.mark.parametrize(
    "defect", ["boolean", "missing", "extra", "unknown_predicate", "mismatched_predicate", "negative"]
)
def test_predicate_schema_and_registry_are_closed(failure_store, kind, defect):
    from evals.regressions import evaluate_regression_fixture

    _, evidence, predicate, controls, _ = proposal_inputs(failure_store, kind)
    fixture = copy.deepcopy(controls["known_good"])
    if defect == "boolean":
        fixture["generation"] = True
    elif defect == "missing":
        fixture.pop("generation")
    elif defect == "extra":
        fixture["source"] = "print('execute')"
    elif defect == "negative":
        fixture["generation"] = -1
    elif defect == "unknown_predicate":
        predicate = "os.system"
    elif defect == "mismatched_predicate":
        predicate = (
            "dispatch.unknown_accounting.v1"
            if kind == "failed_verification"
            else "verification.exact_binding.v1"
        )
    with pytest.raises(ValueError):
        evaluate_regression_fixture(predicate, fixture, evidence=evidence)


def test_well_formed_wrong_verification_outcome_and_unknown_state_are_false(failure_store):
    from evals.regressions import evaluate_regression_fixture

    _, evidence, predicate, controls, _ = proposal_inputs(failure_store, "failed_verification")
    assert (
        evaluate_regression_fixture(
            predicate, {**controls["known_good"], "outcome": "pass"}, evidence=evidence
        )
        is False
    )
    # Different submission key avoids overwriting first fixture.
    failure_store.cancel("tenant", evidence.verify()["scope"]["task_id"], "fixture-cleanup")


@pytest.mark.parametrize("record_kind", ["case", "review"])
@pytest.mark.parametrize("defect", ["noncanonical", "wrong_digest", "extra", "heldout"])
def test_direct_record_construction_rejects_identity_or_promotion(failure_store, record_kind, defect):
    from evals.regressions import RegressionCase, RegressionReview, record_regression_review

    _, evidence, predicate, _, ref = proposal_inputs(failure_store, "unknown_dispatch")
    case = freeze(failure_store, evidence, predicate, ref)
    record = (
        case
        if record_kind == "case"
        else record_regression_review(
            case,
            reviewer_id="test",
            reviewer_kind="ai",
            disposition="approved",
            reasons=["declared review"],
            reviewed_at=1,
        )
    )
    data = record.read()
    if defect == "extra":
        data["accepted"] = True
    elif defect == "heldout":
        if record_kind == "case":
            data["lineage"]["split"] = "held_out"
        else:
            data["authority"] = "production_acceptance"
    payload = json.dumps(data, indent=1).encode() if defect == "noncanonical" else canonical_bytes(data)
    cls = RegressionCase if record_kind == "case" else RegressionReview
    with pytest.raises(ValueError):
        cls(payload, "f" * 64 if defect == "wrong_digest" else digest_bytes(payload)).verify()


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewer_kind", "system"),
        ("disposition", "accepted"),
        ("reasons", []),
        ("reasons", ["x"] * 17),
        ("reviewed_at", True),
        ("reviewed_at", float("nan")),
    ],
)
def test_review_schema_strict(failure_store, field, value):
    from evals.regressions import record_regression_review

    _, evidence, predicate, _, ref = proposal_inputs(failure_store, "unknown_dispatch")
    case = freeze(failure_store, evidence, predicate, ref)
    args = {
        "reviewer_id": "test",
        "reviewer_kind": "ai",
        "disposition": "approved",
        "reasons": ["data only"],
        "reviewed_at": 1,
    }
    with pytest.raises(ValueError):
        record_regression_review(case, **{**args, field: value})


def test_incomplete_evidence_cannot_be_proposed_even_with_matching_fixture(failure_store):
    from evals.regressions import evaluate_regression_fixture, freeze_regression_case

    task, dispatch = unknown_dispatch(failure_store)
    evidence = extract(failure_store, task, "unknown_dispatch", "missing-subject")
    assert evidence.verify()["status"] == "incomplete"
    valid = extract(failure_store, task, "unknown_dispatch", dispatch)
    predicate, controls = fixtures_for(valid)
    controls["evidence_digest"] = evidence.digest
    ref = failure_store.artifact_store.put_json("tenant", task["task_id"], controls)
    with pytest.raises(ValueError):
        evaluate_regression_fixture(predicate, controls["known_good"], evidence=evidence)
    with pytest.raises(ValueError):
        freeze_regression_case(
            evidence,
            fixture_ref=ref,
            predicate_id=predicate,
            source_hashes={"source": "a" * 64},
            artifact_reader=failure_store.artifact_store.get,
        )


def test_oversized_fixture_rejected_before_artifact_reader(failure_store):
    from evals.regressions import freeze_regression_case

    _, evidence, predicate, _, ref = proposal_inputs(failure_store, "unknown_dispatch")
    calls = []

    def reader(*args):
        calls.append(args)
        raise AssertionError("oversized fixture must reject before read")

    with pytest.raises(ValueError):
        freeze_regression_case(
            evidence,
            fixture_ref={**ref, "size": 65537},
            predicate_id=predicate,
            source_hashes={"source": "a" * 64},
            artifact_reader=reader,
        )
    assert calls == []


def test_adapter_paths_never_launch_process_network_or_write_runtime(failure_store, monkeypatch):
    import socket
    import subprocess
    from evals.regressions import evaluate_regression_fixture, record_regression_review

    _, evidence, predicate, controls, ref = proposal_inputs(failure_store, "unknown_dispatch")
    before = fingerprint(failure_store)

    def prohibited(*args, **kwargs):
        raise AssertionError("adapter attempted execution, network, or authority mutation")

    monkeypatch.setattr(socket.socket, "connect", prohibited)
    monkeypatch.setattr(subprocess, "Popen", prohibited)
    for method in (
        "record_verification",
        "publish_review",
        "record_review",
        "begin_dispatch",
        "finish_dispatch",
        "submit",
        "claim",
        "fail_execution",
        "cancel",
    ):
        monkeypatch.setattr(failure_store, method, prohibited)
    assert evaluate_regression_fixture(predicate, controls["known_good"], evidence=evidence)
    case = freeze(failure_store, evidence, predicate, ref)
    record_regression_review(
        case,
        reviewer_id="test",
        reviewer_kind="ai",
        disposition="approved",
        reasons=["declared data review"],
        reviewed_at=1,
    )
    assert fingerprint(failure_store) == before
