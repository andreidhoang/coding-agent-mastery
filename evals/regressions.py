"""Pure data regressions and declared reviews; neither grants runtime authority.

A satisfied predicate checks attribution/accounting in a development fixture.
It does not execute a candidate or change a failed verdict into a passing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from service.artifacts import canonical_bytes, digest_bytes, digest_json
from service.contracts import digest, identity, strict_int

from .evidence import (
    FailureEvidence,
    load_json_bytes,
    validate_artifact_ref,
    validate_canonical_record,
    validate_lineage,
    validate_source_hashes,
)
from .validation import finite_real


_FIXTURE_LIMIT = 64 * 1024
_TRUST = "local_caller_asserted_not_authenticated"
_VERIFICATION_KEYS = frozenset({
    "contract_digest", "base_revision", "candidate_id", "tree_digest",
    "grader_digest", "environment_digest", "verification_id", "generation", "outcome",
})
_DISPATCH_KEYS = frozenset({
    "dispatch_id", "generation", "effect_state", "billing_state", "bound_units", "actual_units",
    "spent_units", "reserved_units", "attempt_allowance_units", "unsettled_bound_units",
})
# This closed table contains constants only: no imported/user-supplied execution.
_PREDICATES = {
    "verification.exact_binding.v1": (
        "failed_verification", "complete_failed_verification",
        "Failed verification is bound to the exact contract, candidate tree, grader, environment and generation.",
        _VERIFICATION_KEYS,
    ),
    "dispatch.unknown_accounting.v1": (
        "unknown_dispatch", "complete_unknown_dispatch",
        "Unknown dispatch retains separate effect and billing states and exact whole-task accounting.",
        _DISPATCH_KEYS,
    ),
}
_CASE_KEYS = frozenset({
    "schema", "evidence_kind", "evidence_digest", "fixture_ref", "fixture_digest", "predicate_id",
    "precondition", "invariant", "known_good_digest", "known_bad_digest", "control_results",
    "source_hashes", "fix_revision", "lineage", "review_state", "trust",
})
_REVIEW_KEYS = frozenset({
    "schema", "evidence_kind", "case_digest", "reviewer_id", "reviewer_kind", "disposition",
    "reasons", "reviewed_at", "authority",
})


def _object(value, keys, name):
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"invalid {name} schema")
    return value


def _text(value, name, maximum):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"invalid {name}")
    return value


def _predicate(predicate_id):
    if type(predicate_id) is not str or predicate_id not in _PREDICATES:
        raise ValueError("unsupported regression predicate")
    return _PREDICATES[predicate_id]


def _json_copy(value):
    try:
        encoded = canonical_bytes(value)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("regression data must be finite JSON") from exc
    return load_json_bytes(encoded)


def _validate_fixture(predicate_id, fixture):
    _, _, _, keys = _predicate(predicate_id)
    _object(fixture, keys, "regression fixture")
    strict_int(fixture["generation"], "generation", 1)
    if predicate_id == "verification.exact_binding.v1":
        for field in ("contract_digest", "tree_digest", "grader_digest", "environment_digest"):
            digest(fixture[field], field)
        for field in ("candidate_id", "verification_id"):
            identity(fixture[field], field)
        _text(fixture["base_revision"], "base_revision", 512)
        if fixture["outcome"] not in ("pass", "fail", "error"):
            raise ValueError("invalid fixture outcome")
    else:
        identity(fixture["dispatch_id"], "dispatch_id")
        if fixture["effect_state"] not in (
            "in_flight", "succeeded", "failed_known", "unknown", "not_dispatched",
        ):
            raise ValueError("invalid fixture effect_state")
        if fixture["billing_state"] not in ("reserved", "liability_unknown", "settled"):
            raise ValueError("invalid fixture billing_state")
        strict_int(fixture["bound_units"], "bound_units")
        for field in (
            "spent_units", "reserved_units", "attempt_allowance_units", "unsettled_bound_units",
        ):
            if type(fixture[field]) is not int or fixture[field] < 0:
                raise ValueError("invalid nonnegative aggregate " + field)
        if fixture["actual_units"] is not None:
            strict_int(fixture["actual_units"], "actual_units")
    # Clone before comparison, rejecting every non-JSON/nonfinite input.
    return _json_copy(fixture)


def _verified_evidence(evidence):
    if not isinstance(evidence, FailureEvidence):
        raise ValueError("regression requires FailureEvidence")
    data = evidence.verify()
    if data["status"] != "complete" or data["regression_eligible"] is not True:
        raise ValueError("evidence is not regression eligible")
    return data


def _expected(predicate_id, data):
    kind, _, _, _ = _predicate(predicate_id)
    if data["kind"] != kind:
        raise ValueError("predicate does not match evidence kind")
    subject = data["subject"]
    if kind == "failed_verification":
        expected = {key: data["identities"][key] for key in (
            "contract_digest", "base_revision", "candidate_id", "tree_digest",
            "grader_digest", "environment_digest",
        )}
        expected.update({key: subject[key] for key in ("verification_id", "generation", "outcome")})
    else:
        selected = [
            row for row in data["accounting"]["dispatches"]
            if row["dispatch_id"] == subject["dispatch_id"]
        ]
        if len(selected) != 1:
            raise ValueError("selected dispatch missing or ambiguous")
        dispatch = selected[0]
        expected = {key: dispatch[key] for key in (
            "dispatch_id", "generation", "effect_state", "billing_state", "bound_units", "actual_units",
        )}
        expected.update({key: data["accounting"][key] for key in (
            "spent_units", "reserved_units", "attempt_allowance_units", "unsettled_bound_units",
        )})
    return _validate_fixture(predicate_id, expected)


def evaluate_regression_fixture(predicate_id, fixture, *, evidence) -> bool:
    """Return whether the fixed data invariant is satisfied, never a grader verdict."""
    data = _verified_evidence(evidence)
    expected = _expected(predicate_id, data)
    actual = _validate_fixture(predicate_id, fixture)
    return actual == expected


def _validate_case(data):
    _object(data, _CASE_KEYS, "regression case")
    if type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("unsupported regression case schema")
    if data["evidence_kind"] != "development_regression_case":
        raise ValueError("invalid regression case evidence_kind")
    _, precondition, invariant, _ = _predicate(data["predicate_id"])
    if data["precondition"] != precondition or data["invariant"] != invariant:
        raise ValueError("regression predicate constants disagree")
    for field in ("evidence_digest", "fixture_digest", "known_good_digest", "known_bad_digest"):
        digest(data[field], field)
    if data["known_good_digest"] == data["known_bad_digest"]:
        raise ValueError("regression controls must be distinct")
    ref = data["fixture_ref"]
    if type(ref) is not dict:
        raise ValueError("invalid fixture_ref")
    validate_artifact_ref(ref, ref.get("tenant_id"), ref.get("task_id"), max_bytes=_FIXTURE_LIMIT)
    if data["fixture_digest"] != ref["digest"]:
        raise ValueError("fixture digest mismatch")
    controls = _object(data["control_results"], {"known_good", "known_bad"}, "control_results")
    if controls["known_good"] is not True or controls["known_bad"] is not False:
        raise ValueError("invalid regression control results")
    validate_source_hashes(data["source_hashes"])
    validate_lineage(data["lineage"])
    if data["fix_revision"] is not None:
        _text(data["fix_revision"], "fix_revision", 128)
    if data["review_state"] != "pending" or data["trust"] != _TRUST:
        raise ValueError("invalid regression case authority")


@dataclass(frozen=True, slots=True)
class RegressionCase:
    payload: bytes
    digest: str

    def __post_init__(self):
        self.verify()

    @classmethod
    def freeze(cls, data):
        data = _json_copy(data)
        _validate_case(data)
        payload = canonical_bytes(data)
        return cls(payload, digest_bytes(payload))

    def read(self):
        return self.verify()

    def verify(self):
        return validate_canonical_record(self.payload, self.digest, _validate_case)


def freeze_regression_case(
    evidence, *, fixture_ref, predicate_id, source_hashes,
    artifact_reader: Callable[[str, str, str], bytes], fix_revision=None,
) -> RegressionCase:
    """Freeze caller-authored good/bad data controls as a pending development proposal."""
    data = _verified_evidence(evidence)
    _expected(predicate_id, data)
    validate_source_hashes(source_hashes)
    if fix_revision is not None:
        _text(fix_revision, "fix_revision", 128)
    scope = data["scope"]
    ref = validate_artifact_ref(
        fixture_ref, scope["tenant_id"], scope["task_id"], max_bytes=_FIXTURE_LIMIT,
    )
    # Copy caller-owned metadata before invoking the trusted external reader.
    ref = _json_copy(ref)
    hashes = _json_copy(source_hashes)
    if not callable(artifact_reader):
        raise ValueError("artifact_reader must be callable")
    raw = artifact_reader(ref["tenant_id"], ref["task_id"], ref["digest"])
    if type(raw) is not bytes or len(raw) > _FIXTURE_LIMIT:
        raise ValueError("fixture artifact exceeds byte contract")
    if len(raw) != ref["size"] or digest_bytes(raw) != ref["digest"]:
        raise ValueError("fixture artifact integrity mismatch")
    fixture = _object(load_json_bytes(raw), {
        "schema", "evidence_digest", "predicate_id", "known_good", "known_bad",
    }, "fixture artifact")
    if type(fixture["schema"]) is not int or fixture["schema"] != 1:
        raise ValueError("unsupported fixture artifact schema")
    digest(fixture["evidence_digest"], "evidence_digest")
    if fixture["evidence_digest"] != evidence.digest or fixture["predicate_id"] != predicate_id:
        raise ValueError("fixture artifact binding mismatch")
    good = _validate_fixture(predicate_id, fixture["known_good"])
    bad = _validate_fixture(predicate_id, fixture["known_bad"])
    good_digest, bad_digest = digest_json(good), digest_json(bad)
    if good_digest == bad_digest:
        raise ValueError("regression controls must be distinct")
    if not evaluate_regression_fixture(predicate_id, good, evidence=evidence):
        raise ValueError("known_good predicate is not satisfied")
    if evaluate_regression_fixture(predicate_id, bad, evidence=evidence):
        raise ValueError("known_bad predicate is satisfied")
    _, precondition, invariant, _ = _predicate(predicate_id)
    return RegressionCase.freeze({
        "schema": 1, "evidence_kind": "development_regression_case",
        "evidence_digest": evidence.digest, "fixture_ref": ref, "fixture_digest": digest_bytes(raw),
        "predicate_id": predicate_id, "precondition": precondition, "invariant": invariant,
        "known_good_digest": good_digest, "known_bad_digest": bad_digest,
        "control_results": {"known_good": True, "known_bad": False}, "source_hashes": hashes,
        "fix_revision": fix_revision, "lineage": data["lineage"], "review_state": "pending", "trust": _TRUST,
    })


def _validate_review(data):
    _object(data, _REVIEW_KEYS, "regression review")
    if type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("unsupported regression review schema")
    if data["evidence_kind"] != "development_regression_review":
        raise ValueError("invalid regression review evidence_kind")
    digest(data["case_digest"], "case_digest")
    identity(data["reviewer_id"], "reviewer_id")
    if data["reviewer_kind"] not in ("human", "ai"):
        raise ValueError("invalid reviewer_kind")
    if data["disposition"] not in ("approved", "rejected"):
        raise ValueError("invalid review disposition")
    reasons = data["reasons"]
    if type(reasons) is not list or not 1 <= len(reasons) <= 16:
        raise ValueError("review reasons must contain 1..16 strings")
    for reason in reasons:
        _text(reason, "review reason", 2048)
    finite_real(data["reviewed_at"], "reviewed_at", minimum=0)
    if data["authority"] != "caller_declared_review_only":
        raise ValueError("invalid regression review authority")


@dataclass(frozen=True, slots=True)
class RegressionReview:
    payload: bytes
    digest: str

    def __post_init__(self):
        self.verify()

    @classmethod
    def freeze(cls, data):
        data = _json_copy(data)
        _validate_review(data)
        payload = canonical_bytes(data)
        return cls(payload, digest_bytes(payload))

    def read(self):
        return self.verify()

    def verify(self):
        return validate_canonical_record(self.payload, self.digest, _validate_review)


def record_regression_review(
    case, *, reviewer_id, reviewer_kind, disposition, reasons, reviewed_at,
) -> RegressionReview:
    """Create a separate caller-declared review without changing the pending case."""
    if not isinstance(case, RegressionCase):
        raise ValueError("review requires RegressionCase")
    case.verify()
    return RegressionReview.freeze({
        "schema": 1, "evidence_kind": "development_regression_review", "case_digest": case.digest,
        "reviewer_id": reviewer_id, "reviewer_kind": reviewer_kind, "disposition": disposition,
        "reasons": reasons, "reviewed_at": reviewed_at, "authority": "caller_declared_review_only",
    })
