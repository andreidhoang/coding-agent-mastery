"""Product evidence claims must track committed identities and exact public bytes."""

import json
from copy import deepcopy
from html.parser import HTMLParser

import pytest

from service.artifacts import LocalArtifacts, digest_bytes, digest_json
from service.integration import candidate_manifest
from service.repair_reporting import write_repair_report


@pytest.fixture
def evidence(tmp_path):
    artifacts = LocalArtifacts(tmp_path / "public")
    manifest = candidate_manifest({"slug.py": "old\n"}, {"slug.py": "fixed café\r\n"},
                                  ["slug.py"], {}, ["Fix slug"])
    grader, environment, contract = (digest_json(x) for x in ("grader", "environment", "contract"))
    receipt = {"phase": "final", "passed": True, "outcome": "pass", "mode": "injected_test_only",
               "tree_digest": manifest["tree_digest"], "grader_digest": grader,
               "environment_digest": environment,
               "cases": [{"id": "private-1", "passed": True, "category": "pass"}],
               "expect": "DO NOT RENDER RAW ASSERTIONS"}
    ref = artifacts.put_json("repair", "task", receipt)
    snapshot = {
        "task": {"task_id": "task", "tenant_id": "repair", "generation": 1,
                 "head_candidate_id": "head", "head_revision": 1, "execution_state": "review_eligible",
                 "review_state": "pending", "contract_digest": contract,
                 "contract": {"model": "NVIDIA/mock", "profile": "production", "patch_slot_limit": 1,
                              "requirements": ["Fix slug"], "grader_digest": grader,
                              "environment_digest": environment, "repair_spec": {"max_worker_tests": 4}}},
        "candidates": [{"candidate_id": "head", "kind": "integration", "tree_digest": manifest["tree_digest"],
                        "manifest": manifest}],
        "verifications": [{"verification_id": "verification", "tenant_id": "repair", "task_id": "task",
                           "generation": 1, "candidate_id": "head", "contract_digest": contract,
                           "outcome": "pass", "tree_digest": manifest["tree_digest"],
                           "grader_digest": grader, "environment_digest": environment,
                           "authority": "trusted-control-plane", "evidence_ref": ref, "recorded_at": 1}],
        "budget": {"spent": 12, "reserved": 0, "limit": 100}, "frontier": {}, "nodes": [],
        "dispatches": [], "reviews": [], "sandboxes": [],
        "evidence_kind": "native_mock_transport_supported_repair", "repair_scope": "Stateless functions",
    }
    return snapshot, artifacts


def test_offline_report_writes_exact_patch_and_detached_result(tmp_path, evidence):
    snapshot, artifacts = evidence
    output = tmp_path / "report"
    events = [{"kind": "head.integrated", "sequence": 1}]
    report = write_repair_report(output, snapshot, events, artifacts=artifacts)
    assert report["verified"] is True
    assert report["review_state"] == "pending"
    patch = snapshot["candidates"][0]["manifest"]["patch"].encode()
    assert (output / "change.patch").read_bytes() == patch
    assert report["downloads"]["patch"]["sha256"] == digest_bytes(patch)
    assert report["downloads"]["patch"]["bytes"] == len(patch)
    assert json.loads((output / "repair.json").read_text()) == report
    assert {"snapshot.json", "trace.json", "trace.html", "repair.html", "repair.json", "change.patch"} <= {
        p.name for p in output.iterdir()
    }
    assert "DO NOT RENDER RAW ASSERTIONS" not in (output / "repair.html").read_text()
    snapshot["candidates"][0]["manifest"]["changed_paths"].append("later.py")
    events[0]["kind"] = "mutated"
    assert report["candidate"]["changed_paths"] == ["slug.py"]
    assert report["progress"][0]["kind"] == "head.integrated"
    report["budget"]["spent"] = 200
    assert snapshot["budget"]["spent"] == 12


@pytest.mark.parametrize("field,value", [
    ("tree_digest", "stale"), ("candidate_id", "worker"), ("grader_digest", "other"),
    ("environment_digest", "other"), ("generation", 2), ("contract_digest", "other"),
    ("tenant_id", "other"), ("task_id", "other"), ("authority", "worker"),
])
def test_stale_receipt_cannot_claim_verified(tmp_path, evidence, field, value):
    snapshot, artifacts = evidence
    snapshot["verifications"][0][field] = value
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert report["independent_tests"]["status"] == "unverified"


def test_current_tree_bytes_must_match_head_identity(tmp_path, evidence):
    snapshot, artifacts = evidence
    snapshot["candidates"][0]["manifest"]["files"]["slug.py"] = "different"
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert report["candidate"]["patch_available"] is False


def test_no_head_candidate_only_and_no_candidate(tmp_path, evidence):
    snapshot, artifacts = evidence
    snapshot["task"]["head_candidate_id"] = None
    snapshot["task"]["execution_state"] = "failed"
    snapshot["candidates"][0]["kind"] = "worker"
    report = write_repair_report(tmp_path / "candidate", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert report["candidate"]["patch_label"] == "Candidate only; unverified"
    assert (tmp_path / "candidate/change.patch").read_bytes() == snapshot["candidates"][0]["manifest"]["patch"].encode()
    snapshot["candidates"] = []
    report = write_repair_report(tmp_path / "empty", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert report["downloads"]["patch"]["available"] is False
    assert (tmp_path / "empty/change.patch").read_bytes() == b""
    assert "Patch download unavailable" in (tmp_path / "empty/repair.html").read_text()


@pytest.mark.parametrize("recorded_at", [1, 2])
def test_latest_exact_failed_receipt_prevents_pass_claim(tmp_path, evidence, recorded_at):
    snapshot, artifacts = evidence
    failed = deepcopy(snapshot["verifications"][0])
    failed.update(outcome="fail", recorded_at=recorded_at, verification_id="new")
    public = artifacts.get_json("repair", "task", failed["evidence_ref"]["digest"])
    public.update(outcome="fail", passed=False, cases=[{"id": "private-1", "passed": False, "category": "mismatch"}])
    failed["evidence_ref"] = artifacts.put_json("repair", "task", public)
    snapshot["verifications"].append(failed)
    snapshot["task"]["execution_state"] = "failed"
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert report["independent_tests"]["status"] == "fail"
    assert report["independent_tests"]["cases"][0]["passed"] is False


def test_public_artifact_missing_is_clear_without_private_store_reads(tmp_path, evidence):
    snapshot, artifacts = evidence
    ref = snapshot["verifications"][0]["evidence_ref"]
    artifacts._path("repair", "task", ref["digest"]).unlink()
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["independent_tests"]["evidence_available"] is False
    assert "unavailable" in report["independent_tests"]["evidence_availability"]
    assert report["independent_tests"]["cases"] == []
    # The committed receipt summary remains distinct from unavailable artifact details.
    assert report["independent_tests"]["receipt"]["outcome"] == "pass"


def test_conflicting_public_artifact_cannot_support_verification(tmp_path, evidence):
    snapshot, artifacts = evidence
    ref = artifacts.put_json("repair", "task", {"phase": "worker", "passed": True})
    snapshot["verifications"][0]["evidence_ref"] = ref
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert "conflicts" in report["independent_tests"]["message"]


def test_cumulative_worker_requests_and_unknown_reserved_are_separate(tmp_path, evidence):
    snapshot, artifacts = evidence
    snapshot["dispatches"] = [
        {"kind": "run_tests", "attempt_id": "old", "effect_state": "succeeded", "billing_state": "settled"},
        {"kind": "run_tests", "attempt_id": "new", "effect_state": "unknown", "billing_state": "reserved", "bound_units": 5},
        {"kind": "model.nebius", "effect_state": "unknown", "billing_state": "reserved", "bound_units": 7},
        {"kind": "model.nebius", "effect_state": "unknown", "billing_state": "settled", "bound_units": 9},
    ]
    snapshot["budget"].update(reserved=20)
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["worker_tests"]["count"] == 2
    assert report["worker_tests"]["unknown"] == 1
    assert report["budget"]["spent"] == 12
    assert report["budget"]["unknown_reserved"] == 12
    assert report["budget"]["unknown_effects"] == 3
    assert report["budget"]["other_reserved"] == 8


class DocumentInspection(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)


def test_issue_patch_and_receipt_strings_are_inert_offline(tmp_path, evidence):
    snapshot, artifacts = evidence
    injection = '</script><script src="https://attacker.invalid/x">alert(1)</script><img onerror="alert(2)">'
    snapshot["task"]["contract"]["requirements"][0] = injection
    snapshot["candidates"][0]["manifest"]["patch"] = injection
    report = write_repair_report(tmp_path / "report", snapshot, [{"kind": injection}], artifacts=artifacts)
    document = (tmp_path / "report/repair.html").read_text()
    parsed = DocumentInspection()
    parsed.feed(document)
    assert parsed.tags.count("script") == 1
    assert "img" not in parsed.tags
    assert not any(name in {"src", "onerror", "onclick"} for name, _ in parsed.attrs)
    assert all(not value.startswith(("http:", "https:")) for name, value in parsed.attrs if name == "href")
    assert "&lt;/script&gt;" in document
    embedded = document.split('<script type="application/json" id="repair-data">')[1].split("</script>")[0]
    assert json.loads(embedded) == report
    assert injection not in embedded
    assert (tmp_path / "report/change.patch").read_bytes() == injection.encode()


def test_operator_configuration_does_not_claim_live_model_capability(tmp_path, evidence):
    snapshot, artifacts = evidence
    snapshot["evidence_kind"] = "operator_configured_provider_repair; inspect actual request receipts"
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["evidence_label"].startswith("Operator configured provider")
    assert "actual model capability" in " ".join(report["limits"])
    assert "human mastery" in " ".join(report["limits"]).lower()
    assert "Recorded event order · Operator configured provider" in (tmp_path / "report/trace.html").read_text()
    assert "Measured event order · scripted fixture" not in (tmp_path / "report/trace.html").read_text()


@pytest.mark.parametrize("outcome", ["fail", "error"])
def test_terminal_generation_revocation_displays_exact_bound_failure(tmp_path, evidence, outcome):
    snapshot, artifacts = evidence
    record = snapshot["verifications"][0]
    receipt = artifacts.get_json("repair", "task", record["evidence_ref"]["digest"])
    receipt.update(passed=False, outcome=outcome,
                   cases=[{"id": "private-1", "passed": False, "category": "boundary"}])
    record.update(outcome=outcome, evidence_ref=artifacts.put_json("repair", "task", receipt))
    snapshot["task"].update(generation=2, execution_state="failed", failure={
        "generation": 1, "reason": "candidate_failed", "evidence_ref": record["evidence_ref"],
    })
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert report["independent_tests"]["status"] == outcome
    assert report["independent_tests"]["receipt"]["generation"] == 1
    assert report["independent_tests"]["evidence_available"] is True
    assert report["independent_tests"]["cases"][0]["passed"] is False


@pytest.mark.parametrize("outcome,bind_ref", [("pass", True), ("fail", False), ("error", False)])
def test_revocation_does_not_promote_historical_pass_or_unbound_failure(tmp_path, evidence, outcome, bind_ref):
    snapshot, artifacts = evidence
    record = snapshot["verifications"][0]
    record["outcome"] = outcome
    failure_ref = record["evidence_ref"] if bind_ref else artifacts.put_json("repair", "task", {"other": True})
    snapshot["task"].update(generation=2, execution_state="failed", failure={
        "generation": 1, "reason": "candidate_failed", "evidence_ref": failure_ref,
    })
    report = write_repair_report(tmp_path / "report", snapshot, [], artifacts=artifacts)
    assert report["verified"] is False
    assert report["independent_tests"]["status"] == "unverified"
    assert report["independent_tests"]["receipt"] is None
