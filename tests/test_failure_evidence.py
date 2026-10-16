"""Semantic extraction controls use actual committed verifier and dispatch fixtures."""

import copy
import json

import pytest

from failure_adapter_helpers import (
    LINEAGE,
    PROVENANCE,
    capture,
    extract,
    failed_verification,
    failure_store,
    fingerprint,
    fixtures_for,
    refresh_metadata,
    unknown_dispatch,
)
from service.artifacts import canonical_bytes, digest_bytes, digest_json

assert failure_store


def test_actual_failed_verification_preserves_causal_generation(failure_store):
    task, verification, ref, result = failed_verification(failure_store)
    evidence = extract(failure_store, task, "failed_verification", verification["verification_id"])
    data = evidence.verify()
    assert data["status"] == "complete", data["reasons"]
    assert data["regression_eligible"] is True
    assert data["subject"]["generation"] == verification["generation"] == 1
    assert data["scope"]["current_generation"] == 2
    assert data["subject"]["outcome"] == "fail"
    assert data["identities"]["tree_digest"] == result["tree_digest"]
    assert ref["digest"] in {row["digest"] for row in data["artifacts"]}
    assert data["trust"] == "local_caller_asserted_not_authenticated"
    assert data["assignment"] is None
    assert data["unavailable"]["assignment"] == "unassigned_local_run"


@pytest.mark.parametrize("settled,spent,reserved,unsettled", [(False, 0, 12, 12), (True, 9, 0, 0)])
def test_unknown_keeps_effect_and_billing_separate(failure_store, settled, spent, reserved, unsettled):
    task, dispatch = unknown_dispatch(failure_store, settled=settled)
    data = extract(failure_store, task, "unknown_dispatch", dispatch).verify()
    assert data["status"] == "complete", data["reasons"]
    assert data["subject"]["effect_state"] == "unknown"
    assert data["subject"]["billing_state"] == ("settled" if settled else "liability_unknown")
    account = data["accounting"]
    assert (account["spent_units"], account["reserved_units"], account["unsettled_bound_units"]) == (
        spent,
        reserved,
        unsettled,
    )
    assert account["attempt_allowance_units"] == 0
    assert account["unit"] == "runtime_budget_units"
    assert account["input_tokens"] is account["output_tokens"] is account["infrastructure_cost"] is None


def test_all_node_costs_survive_narrow_selection_and_idempotent_receipts(failure_store):
    task, dispatch = unknown_dispatch(failure_store, all_nodes=True)
    source = capture(failure_store, task)
    event = next(e for e in reversed(source["events"]) if e["kind"] == "dispatch.receipt")
    data = extract(
        failure_store,
        task,
        "unknown_dispatch",
        dispatch,
        source=source,
        window={"start_sequence": event["sequence"], "end_sequence": event["sequence"]},
    ).verify()
    assert data["status"] == "complete", data["reasons"]
    account = data["accounting"]
    assert account["spent_units"] == 20
    assert account["reserved_units"] == 0
    assert sorted(row["actual_units"] for row in account["dispatches"]) == [3, 7, 10]
    assert {row["node_id"] for row in account["dispatches"]} == {"parent", "child", "summary"}
    assert len(source["receipts"]) == len(account["dispatches"]) == 3
    assert all("role" not in row for row in account["dispatches"])


def test_receipt_knowledge_retains_prior_artifact_across_late_null_reference(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    ref = failure_store.artifact_store.put_json("tenant", task["task_id"], {"opaque": "not instructions"})
    failure_store.finish_dispatch("tenant", dispatch, "observed-output", "unknown", None, ref)
    failure_store.finish_dispatch("tenant", dispatch, "late-bill", "unknown", 9, None)
    data = extract(failure_store, task, "unknown_dispatch", dispatch).verify()
    assert data["status"] == "complete", data["reasons"]
    assert data["accounting"]["spent_units"] == 9
    assert data["artifacts"] == [
        {
            "tenant_id": "tenant",
            "task_id": task["task_id"],
            "digest": ref["digest"],
            "size": ref["size"],
            "status": "verified",
        }
    ]


def test_observation_determinism_detachment_and_no_authority_mutation(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    before = fingerprint(failure_store)
    one = extract(failure_store, task, "unknown_dispatch", dispatch, source=source)
    two = extract(failure_store, task, "unknown_dispatch", dispatch, source=copy.deepcopy(source))
    assert (one.digest, one.payload) == (two.digest, two.payload)
    detached = one.read()
    detached["accounting"]["spent_units"] = 123
    source["snapshot"]["task"]["generation"] = 99
    assert one.verify()["accounting"]["spent_units"] == 0
    assert fingerprint(failure_store) == before


@pytest.mark.parametrize(
    "defect",
    [
        "candidate_tree",
        "grader",
        "environment",
        "contract",
        "receipt_id",
        "cross_tenant",
        "duplicate_dispatch",
        "duplicate_event",
        "duplicate_receipt",
        "event_disagreement",
        "accounting",
    ],
)
def test_semantic_substitution_is_invalid(failure_store, defect):
    if defect in {"candidate_tree", "grader", "environment"}:
        task, verification, _, _ = failed_verification(failure_store)
        kind, subject = "failed_verification", verification["verification_id"]
    else:
        task, subject = unknown_dispatch(failure_store)
        kind = "unknown_dispatch"
    source = capture(failure_store, task)
    snapshot = source["snapshot"]
    if defect == "candidate_tree":
        snapshot["candidates"][0]["manifest"]["files"]["issue_tracker.py"] += "\n# changed bytes\n"
    elif defect in {"grader", "environment"}:
        snapshot["verifications"][0][defect + "_digest"] = "f" * 64
    elif defect == "contract":
        snapshot["task"]["contract_digest"] = "f" * 64
    elif defect == "receipt_id":
        snapshot["dispatches"][0]["receipt_id"] = "substituted-receipt"
    elif defect == "cross_tenant":
        snapshot["attempts"][0]["owner"]["tenant_id"] = "other"
    elif defect == "duplicate_dispatch":
        snapshot["dispatches"].append(copy.deepcopy(snapshot["dispatches"][0]))
    elif defect == "duplicate_receipt":
        source["receipts"].append(copy.deepcopy(source["receipts"][0]))
    elif defect == "duplicate_event":
        source["events"].append(copy.deepcopy(source["events"][0]))
    elif defect == "event_disagreement":
        next(e for e in source["events"] if e["kind"] == "dispatch.receipt")["payload"]["actual_units"] = 0
    elif defect == "accounting":
        snapshot["budget"]["spent"] += 1
    refresh_metadata(source)
    data = extract(failure_store, task, kind, subject, source=source).verify()
    assert data["status"] == "invalid", (defect, data["reasons"])
    assert data["regression_eligible"] is False


@pytest.mark.parametrize(
    "defect",
    [
        "middle_event",
        "prefix_event",
        "mixed_incarnation",
        "missing_candidate_event",
        "missing_subject",
        "outside_window",
    ],
)
def test_missing_or_unavailable_history_never_eligible(failure_store, defect):
    task, verification, _, _ = failed_verification(failure_store)
    source = capture(failure_store, task)
    window = None
    subject = verification["verification_id"]
    if defect in {"middle_event", "prefix_event"}:
        source["events"].pop(0 if defect == "prefix_event" else 2)
    elif defect == "mixed_incarnation":
        source["events"][0]["service_incarnation"] = "old-incarnation"
    elif defect == "missing_candidate_event":
        for event in source["events"]:
            if event["kind"] == "head.integrated":
                event["kind"] = "unknown.unrelated"
    elif defect == "missing_subject":
        subject = "f" * 64
    elif defect == "outside_window":
        window = {"start_sequence": 1, "end_sequence": 1}
    refresh_metadata(source)
    data = extract(failure_store, task, "failed_verification", subject, source=source, window=window).verify()
    assert data["status"] in {"incomplete", "invalid"}
    assert data["regression_eligible"] is False


@pytest.mark.parametrize(
    "artifact_defect,status",
    [
        ("missing", "incomplete"),
        ("wrong_bytes", "invalid"),
        ("wrong_size", "invalid"),
        ("wrong_scope", "invalid"),
        ("oversized_ref", "invalid"),
        ("cpu_observation", "incomplete"),
        ("malformed_json", "invalid"),
        ("wrong_grader", "invalid"),
        ("wrong_environment", "invalid"),
        ("wrong_tree", "invalid"),
        ("nonboolean_pass", "invalid"),
    ],
)
def test_verification_artifact_controls(failure_store, artifact_defect, status):
    task, verification, ref, result = failed_verification(failure_store)
    source = capture(failure_store, task)
    reader = failure_store.artifact_store.get
    if artifact_defect == "missing":

        def reader(*args):
            raise FileNotFoundError("not included in reasons")
    elif artifact_defect == "wrong_bytes":

        def reader(*args):
            return b"wrong"
    elif artifact_defect in {"wrong_size", "wrong_scope", "oversized_ref"}:

        def change_refs(value):
            if isinstance(value, dict):
                if value.get("digest") == ref["digest"] and "size" in value:
                    value[{"wrong_scope": "tenant_id"}.get(artifact_defect, "size")] = (
                        "other"
                        if artifact_defect == "wrong_scope"
                        else 8 * 1024 * 1024 + 1
                        if artifact_defect == "oversized_ref"
                        else ref["size"] + 1
                    )
                for item in value.values():
                    change_refs(item)
            elif isinstance(value, list):
                for item in value:
                    change_refs(item)

        change_refs(source)
    else:
        replacement = dict(result)
        if artifact_defect == "cpu_observation":
            replacement.update(evidence_kind="cpu_numerical_observation", kind="rmsnorm")
        elif artifact_defect == "nonboolean_pass":
            replacement["passed"] = 0
        elif artifact_defect.startswith("wrong_"):
            replacement[artifact_defect[6:] + "_digest"] = "f" * 64
        raw = b"{" if artifact_defect == "malformed_json" else canonical_bytes(replacement)
        new_ref = {**ref, "digest": digest_bytes(raw), "size": len(raw)}
        # Rebind all copies and recompute verification identity, so the format check is exercised.
        row = source["snapshot"]["verifications"][0]
        row["evidence_ref"] = new_ref
        old_id = row["verification_id"]
        row["verification_id"] = digest_json(
            {k: v for k, v in row.items() if k not in {"verification_id", "recorded_at"}}
        )
        for event in source["events"]:
            if event["kind"] == "verification.recorded":
                event["payload"] = copy.deepcopy(row)
        source["snapshot"]["task"]["failure"]["evidence_ref"] = new_ref

        def reader(t, k, sha):
            return raw if sha == new_ref["digest"] else failure_store.artifact_store.get(t, k, sha)

        subject = row["verification_id"]
        assert old_id != subject
    refresh_metadata(source)
    data = extract(
        failure_store,
        task,
        "failed_verification",
        locals().get("subject", verification["verification_id"]),
        source=source,
        artifact_reader=reader,
    ).verify()
    assert data["status"] == status, (artifact_defect, data["reasons"])
    assert data["regression_eligible"] is False


def test_artifact_reader_transport_exception_propagates(failure_store):
    task, verification, _, _ = failed_verification(failure_store)

    def broken_reader(*args):
        raise RuntimeError("storage transport failure")

    with pytest.raises(RuntimeError, match="transport"):
        extract(
            failure_store,
            task,
            "failed_verification",
            verification["verification_id"],
            artifact_reader=broken_reader,
        )


@pytest.mark.parametrize(
    "field,value",
    [("split", "held_out"), ("held_out_eligible", True), ("parent_evidence_digests", ["a" * 64, "a" * 64])],
)
def test_heldout_or_duplicate_lineage_rejected(failure_store, field, value):
    from evals.evidence import extract_failure_evidence

    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    with pytest.raises(ValueError):
        extract_failure_evidence(
            source,
            kind="unknown_dispatch",
            subject_id=dispatch,
            window={"start_sequence": 1, "end_sequence": source["capture"]["frontier"]},
            source_provenance=PROVENANCE,
            lineage={**LINEAGE, field: value},
            artifact_reader=failure_store.artifact_store.get,
        )


@pytest.mark.parametrize("payload_style", ["wrong_digest", "noncanonical", "extra_schema", "heldout"])
def test_direct_record_construction_cannot_bypass_validation(failure_store, payload_style):
    from evals.evidence import FailureEvidence

    task, dispatch = unknown_dispatch(failure_store)
    evidence = extract(failure_store, task, "unknown_dispatch", dispatch)
    payload = evidence.payload
    data = evidence.read()
    if payload_style == "extra_schema":
        data["accepted"] = True
        payload = canonical_bytes(data)
    elif payload_style == "heldout":
        data["lineage"]["split"] = "held_out"
        payload = canonical_bytes(data)
    elif payload_style == "noncanonical":
        payload = json.dumps(data, indent=2).encode()
    digest = "f" * 64 if payload_style == "wrong_digest" else digest_bytes(payload)
    with pytest.raises(ValueError):
        FailureEvidence(payload, digest).verify()


def mapped_manifest(source, *, split="development", changed=None):
    from evals.fixtures import demo_manifest
    from evals.manifest import FrozenManifest, assigned_rows

    data = demo_manifest(tasks_count=1, trials=1, arms=("bare", "coordinated_n1")).read()
    contract = source["snapshot"]["task"]["contract"]
    planned_task = data["tasks"][0]
    planned_task.update(
        repository=contract["repo_id"],
        base_commit=contract["base_revision"],
        grader_digest=contract["grader_digest"],
    )
    if changed:
        planned_task.update(changed)
    data["split"] = split
    data["planned_rows"] = assigned_rows(data["tasks"], 1, data["arms"], data["assignment_seed"])
    return FrozenManifest.freeze(data)


@pytest.mark.parametrize("defect", [None, "base", "grader", "repository", "submission", "heldout"])
def test_optional_manifest_mapping_is_exact_and_preserves_planned_identity(failure_store, defect):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    fields = {"base": "base_commit", "grader": "grader_digest", "repository": "repository"}
    manifest = mapped_manifest(
        source,
        split="held_out" if defect == "heldout" else "development",
        changed={fields[defect]: "f" * 64} if defect in fields else None,
    )
    before = manifest.payload
    row = manifest.read()["planned_rows"][0]
    submission_id = digest_json(["tenant", source["submissions"][0]["key"]])
    assignment = {
        "manifest": manifest,
        "row_id": row["row_id"],
        "runtime_submission_id": "f" * 64 if defect == "submission" else submission_id,
    }
    if defect:
        with pytest.raises(ValueError):
            extract(failure_store, task, "unknown_dispatch", dispatch, source=source, assignment=assignment)
    else:
        data = extract(
            failure_store, task, "unknown_dispatch", dispatch, source=source, assignment=assignment
        ).verify()
        assert data["status"] == "complete", data["reasons"]
        assert data["assignment"]["manifest_digest"] == manifest.digest
        assert data["assignment"]["planned_row"] == row
        assert row["task_id"] != task["task_id"]
        assert data["assignment"]["runtime_submission_id"] == submission_id
        assert data["assignment"]["binding_kind"] == "caller_declared_runtime_mapping"
    assert manifest.payload == before


@pytest.mark.parametrize(
    "defect",
    [
        "source_oversize",
        "boolean_window",
        "unknown_kind",
        "provenance_extra",
        "redaction",
        "absolute_source_hash",
        "nonfinite",
    ],
)
def test_input_metadata_errors_raise(failure_store, defect):
    from evals.evidence import extract_failure_evidence

    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    provenance = copy.deepcopy(PROVENANCE)
    window = {"start_sequence": 1, "end_sequence": source["capture"]["frontier"]}
    kind = "unknown_dispatch"
    if defect == "source_oversize":
        source["padding"] = "x" * 16_777_216
    elif defect == "boolean_window":
        window["start_sequence"] = True
    elif defect == "unknown_kind":
        kind = "cpu_numerical_observation"
    elif defect == "provenance_extra":
        provenance["signed"] = True
    elif defect == "redaction":
        provenance["redactions"] = ["changed"]
    elif defect == "absolute_source_hash":
        provenance["source_hashes"] = {"/absolute": "a" * 64}
    elif defect == "nonfinite":
        source["events"][0]["time"] = float("nan")
    with pytest.raises(ValueError):
        extract_failure_evidence(
            source,
            kind=kind,
            subject_id=dispatch,
            window=window,
            source_provenance=provenance,
            lineage=LINEAGE,
            artifact_reader=failure_store.artifact_store.get,
        )


def test_huge_supplied_frontier_is_bounded_and_ineligible(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    source["snapshot"]["task"]["event_sequence"] = 10**12
    source["snapshot"]["frontier"]["sequence"] = 10**12
    source["capture"]["frontier"] = source["capture"]["history_end"] = 10**12
    refresh_metadata(source)
    data = extract(failure_store, task, "unknown_dispatch", dispatch, source=source).verify()
    assert data["status"] != "complete"
    assert data["regression_eligible"] is False


def test_oversized_timestamp_is_normalized_input_error(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    source["events"][0]["time"] = 10**1000
    refresh_metadata(source)
    data = extract(failure_store, task, "unknown_dispatch", dispatch, source=source).verify()
    assert data["status"] == "invalid"


def test_prior_event_only_artifact_missing_is_incomplete(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    ref = failure_store.artifact_store.put_json("tenant", task["task_id"], {"earlier": "opaque"})
    source = capture(failure_store, task)
    source["events"][0]["payload"]["extra_artifact"] = ref
    refresh_metadata(source)

    def reader(tenant, task_id, sha):
        if sha == ref["digest"]:
            raise FileNotFoundError("missing earlier event evidence")
        return failure_store.artifact_store.get(tenant, task_id, sha)

    data = extract(
        failure_store, task, "unknown_dispatch", dispatch, source=source, artifact_reader=reader
    ).verify()
    assert data["status"] == "incomplete", data["reasons"]
    assert "artifact_missing" in data["reasons"]


def test_artifact_count_cap_rejects_before_reader(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    source["events"][0]["payload"]["extra_artifacts"] = [
        {
            "tenant_id": "tenant",
            "task_id": task["task_id"],
            "digest": f"{i:064x}",
            "size": 1,
            "content_type": "application/octet-stream",
        }
        for i in range(257)
    ]
    refresh_metadata(source)
    calls = []

    def reader(*args):
        calls.append(args)
        return b"x"

    data = extract(
        failure_store, task, "unknown_dispatch", dispatch, source=source, artifact_reader=reader
    ).verify()
    assert data["status"] == "invalid"
    assert "artifact_limit_exceeded" in data["reasons"]
    assert calls == []


@pytest.mark.parametrize(
    "defect",
    [
        "subject_billing",
        "subject_generation",
        "subject_node",
        "subject_attempt",
        "outside_window",
        "selected_not_unknown",
        "unselected_owner",
    ],
)
def test_canonical_observation_cannot_hide_internal_contradictions(failure_store, defect):
    from evals.evidence import FailureEvidence

    task, dispatch = unknown_dispatch(failure_store, all_nodes=True)
    evidence = extract(failure_store, task, "unknown_dispatch", dispatch)
    data = evidence.read()
    if defect == "subject_billing":
        data["subject"]["billing_state"] = "liability_unknown"
    elif defect == "subject_generation":
        data["subject"]["generation"] = 500
    elif defect == "subject_node":
        data["subject"]["node_id"] = "other-node"
    elif defect == "subject_attempt":
        data["subject"]["attempt_id"] = "other-attempt"
    elif defect == "outside_window":
        data["window"] = {"start_sequence": 1, "end_sequence": 1}
    elif defect == "selected_not_unknown":
        next(row for row in data["accounting"]["dispatches"] if row["dispatch_id"] == dispatch)[
            "effect_state"
        ] = "succeeded"
        data["accounting"]["unknown_effect_count"] = 0
    elif defect == "unselected_owner":
        data["accounting"]["dispatches"][0].update(node_id="foreign-node", generation=500)
    payload = canonical_bytes(data)
    with pytest.raises(ValueError):
        FailureEvidence(payload, digest_bytes(payload)).verify()


@pytest.mark.parametrize(
    "defect,status",
    [
        ("bool_table_count", "invalid"),
        ("bool_history_start", "invalid"),
        ("missing_selected_receipt", "incomplete"),
        ("missing_unselected_receipt", "incomplete"),
        ("unselected_receipt", "invalid"),
        ("unselected_intent", "invalid"),
        ("boolean_sequence", "invalid"),
    ],
)
def test_full_history_causal_joins_are_validated_outside_subject_window(failure_store, defect, status):
    task, dispatch = unknown_dispatch(failure_store, all_nodes=True)
    source = capture(failure_store, task)
    if defect == "bool_table_count":
        source["capture"]["table_counts"]["tasks"] = True
    elif defect == "bool_history_start":
        source["capture"]["history_start"] = True
    elif defect in {"missing_selected_receipt", "missing_unselected_receipt"}:
        selected = defect == "missing_selected_receipt"
        source["receipts"].remove(
            next(row for row in source["receipts"] if (row["dispatch_id"] == dispatch) == selected)
        )
        refresh_metadata(source)
    elif defect == "unselected_receipt":
        next(row for row in source["snapshot"]["dispatches"] if row["dispatch_id"] != dispatch)[
            "receipt_id"
        ] = "fabricated"
        refresh_metadata(source)
    elif defect == "unselected_intent":
        next(
            e
            for e in source["events"]
            if e["kind"] == "dispatch.intent" and e["payload"]["dispatch_id"] != dispatch
        )["payload"]["input_digest"] = "f" * 64
        refresh_metadata(source)
    elif defect == "boolean_sequence":
        source["events"][0]["sequence"] = True
        refresh_metadata(source)
    data = extract(failure_store, task, "unknown_dispatch", dispatch, source=source).verify()
    assert data["status"] == status, (defect, data["reasons"])
    assert data["regression_eligible"] is False


@pytest.mark.parametrize("defect", ["integration_revision", "integration_parent", "manifest_owner"])
def test_integrated_candidate_causal_history_cannot_substitute_metadata(failure_store, defect):
    task, verification, _, _ = failed_verification(failure_store)
    source = capture(failure_store, task)
    if defect in {"integration_revision", "integration_parent"}:
        event = next(e for e in source["events"] if e["kind"] == "head.integrated")
        event["payload"]["revision" if defect == "integration_revision" else "parents"] = (
            999 if defect == "integration_revision" else ["invented"]
        )
    else:
        candidate = next(row for row in source["snapshot"]["candidates"] if row["kind"] == "integration")
        candidate["manifest"]["owner"]["node_id"] = "invented"
    refresh_metadata(source)
    data = extract(
        failure_store, task, "failed_verification", verification["verification_id"], source=source
    ).verify()
    assert data["status"] == "invalid", data["reasons"]


def test_non_object_task_is_invalid_not_crash(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    source["snapshot"]["task"] = []
    refresh_metadata(source)
    data = extract(failure_store, task, "unknown_dispatch", dispatch, source=source).verify()
    assert data["status"] == "invalid"
    assert data["regression_eligible"] is False


def test_supported_identity_filename_maps_stay_opaque(failure_store):
    from failure_adapter_helpers import make_task
    from service.integration import candidate_manifest

    base = {"task_id": "text task", "tenant_id": "text tenant", "recorded_at": "text time"}
    task = make_task(failure_store, base=base, nodes=("finished", "pending"))
    grant = failure_store.claim("tenant", task["task_id"], "finished", "claim-finished", 40, 60)
    manifest = candidate_manifest(
        base,
        {**base, "recorded_at": "modified text"},
        list(base),
        grant["owner"],
        task["contract"]["requirements"],
    )
    failure_store.accept_candidate(grant["owner"], manifest)
    pending = failure_store.claim("tenant", task["task_id"], "pending", "claim-pending", 40, 60)
    failure_store.begin_dispatch(
        pending["owner"], "model", "unknown-dispatch", "model.generate", "a" * 64, 12
    )
    failure_store.finish_dispatch("tenant", "unknown-dispatch", "lost", "unknown")
    source = capture(failure_store, task)
    data = extract(failure_store, task, "unknown_dispatch", "unknown-dispatch", source=source).verify()
    assert data["status"] == "complete", data["reasons"]
    assert data["artifacts"] == []


def test_artifact_aggregate_declared_bytes_bound_before_reads(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    source["events"][0]["payload"]["extra_artifacts"] = [
        {
            "tenant_id": "tenant",
            "task_id": task["task_id"],
            "digest": f"{i:064x}",
            "size": 8 * 1024 * 1024,
            "content_type": "application/octet-stream",
        }
        for i in range(5)
    ]
    refresh_metadata(source)
    calls = []

    def reader(*args):
        calls.append(args)
        return b""

    data = extract(
        failure_store, task, "unknown_dispatch", dispatch, source=source, artifact_reader=reader
    ).verify()
    assert data["status"] == "invalid"
    assert "artifact_limit_exceeded" in data["reasons"]
    assert calls == []


def test_duplicate_artifact_size_disagreement_is_invalid_before_reads(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    ref = {
        "tenant_id": "tenant",
        "task_id": task["task_id"],
        "digest": "f" * 64,
        "size": 1,
        "content_type": "application/octet-stream",
    }
    source["events"][0]["payload"]["extra_artifacts"] = [ref, {**ref, "size": 2}]
    refresh_metadata(source)
    calls = []

    def reader(*args):
        calls.append(args)
        return b"x"

    data = extract(
        failure_store, task, "unknown_dispatch", dispatch, source=source, artifact_reader=reader
    ).verify()
    assert data["status"] == "invalid"
    assert "artifact_integrity" in data["reasons"]
    assert calls == []


def test_historical_bound_violation_is_preserved_not_rejected_as_arithmetic(failure_store):
    from failure_adapter_helpers import make_task
    from service.contracts import BudgetExceeded

    task = make_task(failure_store)
    grant = failure_store.claim("tenant", task["task_id"], "patch", "claim", 40, 60)
    failure_store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 12)
    with pytest.raises(BudgetExceeded):
        failure_store.finish_dispatch("tenant", "dispatch", "over-bound", "unknown", 150)
    failure_store.retire_sandbox(
        "tenant", grant["sandbox_id"], {"supervisor": "trusted", "exit_observed": True}
    )
    data = extract(failure_store, task, "unknown_dispatch", "dispatch").verify()
    assert data["status"] == "complete", data["reasons"]
    assert data["accounting"]["spent_units"] == 150
    assert data["accounting"]["reserved_units"] == 0
    assert data["accounting"]["dispatches"][0]["bound_units"] == 12


def test_revoked_generation_unknown_keeps_accounting_generation(failure_store):
    task, dispatch = unknown_dispatch(failure_store)
    ref = failure_store.artifact_store.put_json("tenant", task["task_id"], {"reason": "unknown effect"})
    failure_store.fail_execution("tenant", task["task_id"], 1, "effect_unknown", ref)
    data = extract(failure_store, task, "unknown_dispatch", dispatch).verify()
    assert data["status"] == "complete", data["reasons"]
    assert data["scope"]["current_generation"] == 2
    assert data["subject"]["generation"] == data["accounting"]["dispatches"][0]["generation"] == 1
    assert data["accounting"]["unsettled_bound_units"] == 12


@pytest.mark.parametrize("settled", [False, True])
@pytest.mark.parametrize("defect", ["missing_attempt", "broken_owner"])
def test_invalid_accounting_owner_never_reports_fabricated_zero(failure_store, settled, defect):
    task, dispatch = unknown_dispatch(failure_store, settled=settled)
    source = capture(failure_store, task)
    if defect == "missing_attempt":
        source["snapshot"]["attempts"] = []
    else:
        source["snapshot"]["attempts"][0]["owner"]["attempt_id"] = "foreign-attempt"
    refresh_metadata(source)
    data = extract(failure_store, task, "unknown_dispatch", dispatch, source=source).verify()
    assert data["status"] in {"invalid", "incomplete"}
    assert data["source_digest"] == digest_json(source)
    assert data["regression_eligible"] is False
    fields = (
        "spent_units",
        "reserved_units",
        "attempt_allowance_units",
        "unsettled_bound_units",
        "unknown_effect_count",
    )
    assert {field: data["accounting"][field] for field in fields} == dict.fromkeys(fields)
    assert "accounting_unavailable" in data["reasons"]
    assert all(data["unavailable"]["accounting." + field] == "missing_source" for field in fields)


def test_partial_null_accounting_direct_record_rejected(failure_store):
    from evals.evidence import FailureEvidence

    task, dispatch = unknown_dispatch(failure_store, settled=True)
    data = extract(failure_store, task, "unknown_dispatch", dispatch).read()
    data["accounting"]["spent_units"] = None
    data["unavailable"]["accounting.spent_units"] = "missing_source"
    data["status"] = "invalid"
    data["reasons"] = ["accounting_unavailable"]
    data["regression_eligible"] = False
    raw = canonical_bytes(data)
    with pytest.raises(ValueError):
        FailureEvidence(raw, digest_bytes(raw)).verify()


def test_recognized_synthetic_family_cannot_be_renamed_when_unassigned(failure_store):
    from evals.evidence import extract_failure_evidence

    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    with pytest.raises(ValueError):
        extract_failure_evidence(
            source,
            kind="unknown_dispatch",
            subject_id=dispatch,
            window={"start_sequence": 1, "end_sequence": source["capture"]["frontier"]},
            source_provenance=PROVENANCE,
            lineage={**LINEAGE, "family_id": "renamed-workload"},
            artifact_reader=failure_store.artifact_store.get,
        )


def test_multiple_retained_large_settlements_preserve_aggregate_over_signed64(failure_store):
    from failure_adapter_helpers import make_task
    from service.contracts import BudgetExceeded
    from evals.regressions import evaluate_regression_fixture, freeze_regression_case

    task = make_task(failure_store, nodes=("first", "second"))
    grants = [
        failure_store.claim("tenant", task["task_id"], node, "claim-" + node, 40, 60)
        for node in ("first", "second")
    ]
    for node, grant in zip(("first", "second"), grants):
        failure_store.begin_dispatch(
            grant["owner"], "action-" + node, "dispatch-" + node, "model.generate", "a" * 64, 12
        )
    amount = 2**63 - 1
    for node, grant in zip(("first", "second"), grants):
        with pytest.raises(BudgetExceeded):
            failure_store.finish_dispatch("tenant", "dispatch-" + node, "usage-" + node, "unknown", amount)
        failure_store.retire_sandbox(
            "tenant", grant["sandbox_id"], {"supervisor": "trusted", "exit_observed": True}
        )
    evidence = extract(failure_store, task, "unknown_dispatch", "dispatch-second")
    data = evidence.verify()
    assert data["status"] == "complete", data["reasons"]
    assert data["accounting"]["spent_units"] == amount * 2
    assert data["accounting"]["reserved_units"] == 0
    predicate, controls = fixtures_for(evidence)
    assert evaluate_regression_fixture(predicate, controls["known_good"], evidence=evidence)
    assert not evaluate_regression_fixture(predicate, controls["known_bad"], evidence=evidence)
    ref = failure_store.artifact_store.put_json("tenant", task["task_id"], controls)
    case = freeze_regression_case(
        evidence,
        fixture_ref=ref,
        predicate_id=predicate,
        source_hashes={"fixture": "a" * 64},
        artifact_reader=failure_store.artifact_store.get,
    )
    assert case.verify()["review_state"] == "pending"


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_commit", "f" * 64),
        ("grader_digest", "f" * 64),
        ("schedule_index", True),
        ("arm", "unregistered"),
    ],
)
def test_direct_assignment_projection_cannot_disagree_with_evidence(failure_store, field, value):
    from evals.evidence import FailureEvidence

    task, dispatch = unknown_dispatch(failure_store)
    source = capture(failure_store, task)
    manifest = mapped_manifest(source)
    row = manifest.read()["planned_rows"][0]
    evidence = extract(
        failure_store,
        task,
        "unknown_dispatch",
        dispatch,
        source=source,
        assignment={
            "manifest": manifest,
            "row_id": row["row_id"],
            "runtime_submission_id": digest_json(["tenant", source["submissions"][0]["key"]]),
        },
    )
    data = evidence.read()
    data["assignment"]["planned_row"][field] = value
    payload = canonical_bytes(data)
    with pytest.raises(ValueError):
        FailureEvidence(payload, digest_bytes(payload)).verify()


def test_mutually_consistent_future_owner_history_is_invalid_not_accounting_zero(failure_store):
    task, dispatch = unknown_dispatch(failure_store, settled=True)
    source = capture(failure_store, task)

    def change_generation(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "generation":
                    value[key] = 2
                elif key not in {"files", "base_files"}:
                    change_generation(child)
        elif isinstance(value, list):
            for child in value:
                change_generation(child)

    change_generation(source)
    source["snapshot"]["task"]["generation"] = 1
    refresh_metadata(source)
    data = extract(failure_store, task, "unknown_dispatch", dispatch, source=source).verify()
    assert data["status"] == "invalid", data["reasons"]
    assert data["regression_eligible"] is False
    assert data["accounting"]["spent_units"] is None
    assert data["unavailable"]["accounting.spent_units"] == "missing_source"
