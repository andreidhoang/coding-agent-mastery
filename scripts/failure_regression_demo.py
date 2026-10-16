"""Run trusted local data-invariant controls; no candidate replay or provider call.

Usage: .venv/bin/python scripts/failure_regression_demo.py --output /fresh/path
The output must not exist. Only hash-locked, preauthored FixtureVerifier controls
execute; proposals remain pending and declared AI reviews are separate objects.
"""

from __future__ import annotations

# ruff: noqa: E402

import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa
from evals.evidence import extract_failure_evidence
from evals.regressions import (
    evaluate_regression_fixture,
    freeze_regression_case,
    record_regression_review,
)
from service.artifacts import LocalArtifacts, canonical_bytes, digest_bytes, digest_json
from service.execution import tree_digest
from service.integration import candidate_manifest
from service.storage import RuntimeStore, TABLES, authority, event_rows
from service.verification import FixtureVerifier
from workloads.registry import ROOT as WORKLOAD_ROOT, TARGET_FILES, list_tasks


def write_json(path, value):
    path.write_bytes(canonical_bytes(value) + b"\n")


def store_fingerprint(store):
    with store.engine.connect() as c:
        data = {
            name: [dict(row) for row in c.execute(sa.select(table).order_by(table.c.id)).mappings()]
            for name, table in TABLES.items()
        }
        data["events"] = [
            dict(row) for row in c.execute(sa.select(event_rows).order_by(event_rows.c.event_id)).mappings()
        ]
        data["authority"] = [dict(row) for row in c.execute(sa.select(authority)).mappings()]
    artifacts = {
        str(path.relative_to(store.artifact_store.root)): digest_bytes(path.read_bytes())
        for path in store.artifact_store.root.rglob("*")
        if path.is_file()
    }
    return digest_json(data), artifacts


def new_task(store, key, base, requirements, grader=None, environment=None):
    contract = {
        "repo_id": "synthetic-issue-tracker-v1",
        "base_revision": tree_digest(base),
        "requirements": requirements,
        "budget_units": 100,
        "execution_deadline": time.time() + 600,
        "review_deadline": time.time() + 1200,
    }
    if grader is not None:
        contract["grader_digest"] = grader
        contract["environment_digest"] = environment
    task = store.submit("demo-tenant", key, contract)
    store.set_graph("demo-tenant", task["task_id"], 1, [{"node_id": "patch", "allowed_paths": list(base)}])
    return task


def build_failed_fixture(store):
    definition = list_tasks(split="calibration")[0]
    base = {name: (definition.baseline_path / name).read_text() for name in TARGET_FILES}
    incorrect = {
        name: (WORKLOAD_ROOT / "oracle" / "incorrect" / definition.baseline_id / name).read_text()
        for name in TARGET_FILES
    }
    result = FixtureVerifier().verify(incorrect, definition)
    if result["passed"] is not False:
        raise RuntimeError("frozen incorrect control unexpectedly passed")
    task = new_task(
        store,
        "failed-control",
        base,
        list(definition.requirements),
        result["grader_digest"],
        result["environment_digest"],
    )
    grant = store.claim("demo-tenant", task["task_id"], "patch", "failed-claim", 40, 60)
    manifest = candidate_manifest(base, incorrect, list(base), grant["owner"], list(definition.requirements))
    candidate = store.accept_candidate(grant["owner"], manifest)
    head = store.integrate(
        "demo-tenant", task["task_id"], 1, [candidate["candidate_id"]], 0, candidate["manifest"]
    )
    ref = store.artifact_store.put_json("demo-tenant", task["task_id"], result)
    verification = store.record_verification(
        "demo-tenant",
        task["task_id"],
        1,
        head["candidate_id"],
        head["tree_digest"],
        result["grader_digest"],
        result["environment_digest"],
        "fail",
        ref,
    )
    store.fail_execution("demo-tenant", task["task_id"], 1, "candidate_failed", ref)
    store.retire_sandbox(
        "demo-tenant", grant["sandbox_id"], {"supervisor": "trusted-local-demo", "exit_observed": True}
    )
    return task, verification["verification_id"], ref, result


def build_unknown_fixture(store):
    base = {"solution.py": "def answer(): return 0\n"}
    task = new_task(store, "unknown-control", base, ["trusted local fixture"])
    grant = store.claim("demo-tenant", task["task_id"], "patch", "unknown-claim", 40, 60)
    store.begin_dispatch(grant["owner"], "local-action", "unknown-dispatch", "model.generate", "b" * 64, 12)
    store.finish_dispatch("demo-tenant", "unknown-dispatch", "lost-response", "unknown")
    store.retire_sandbox(
        "demo-tenant", grant["sandbox_id"], {"supervisor": "trusted-local-demo", "exit_observed": True}
    )
    before = store.capture_failure_source("demo-tenant", task["task_id"])
    store.finish_dispatch("demo-tenant", "unknown-dispatch", "late-usage", "unknown", 9)
    store.finish_dispatch("demo-tenant", "unknown-dispatch", "late-usage", "unknown", 9)
    return task, "unknown-dispatch", before


def controls_for(evidence):
    data = evidence.verify()
    if data["kind"] == "failed_verification":
        predicate = "verification.exact_binding.v1"
        good = {
            key: data["identities"][key]
            for key in (
                "contract_digest",
                "base_revision",
                "candidate_id",
                "tree_digest",
                "grader_digest",
                "environment_digest",
            )
        }
        good.update({key: data["subject"][key] for key in ("verification_id", "generation", "outcome")})
        bad = {**good, "tree_digest": "f" * 64}
    else:
        predicate = "dispatch.unknown_accounting.v1"
        row = next(
            item
            for item in data["accounting"]["dispatches"]
            if item["dispatch_id"] == data["subject"]["dispatch_id"]
        )
        good = {
            key: row[key]
            for key in (
                "dispatch_id",
                "generation",
                "effect_state",
                "billing_state",
                "bound_units",
                "actual_units",
            )
        }
        good.update(
            {
                key: data["accounting"][key]
                for key in (
                    "spent_units",
                    "reserved_units",
                    "attempt_allowance_units",
                    "unsettled_bound_units",
                )
            }
        )
        bad = {**good, "spent_units": 0}
    return predicate, {
        "schema": 1,
        "evidence_digest": evidence.digest,
        "predicate_id": predicate,
        "known_good": good,
        "known_bad": bad,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_paths = [
        "service/storage.py",
        "evals/evidence.py",
        "evals/regressions.py",
        "scripts/failure_regression_demo.py",
        "research/failure-regression-spec-2026-10-10.md",
    ]
    source_hashes = {path: digest_bytes((ROOT / path).read_bytes()) for path in source_paths}
    artifacts = LocalArtifacts(output / "artifacts")
    store = RuntimeStore(
        "sqlite:///" + str(output / "runtime.sqlite"),
        artifacts,
        service_budget_units=1000,
        tenant_budget_units=1000,
    )
    try:
        failed_task, verification_id, verifier_ref, verifier_result = build_failed_fixture(store)
        unknown_task, dispatch_id, unknown_before = build_unknown_fixture(store)
        write_json(output / "unknown-unsettled-source.json", unknown_before)
        write_json(output / "verifier-result.json", verifier_result)
        packet = {
            "schema": 1,
            "evidence_kind": "trusted_local_adapter_demo",
            "source_hashes": source_hashes,
            "paid_execution_enabled": False,
            "candidate_replay_executed": False,
            "trusted_frozen_verifier_control_executed": True,
            "observations": [],
            "unknown_accounting_trace": {"unsettled": unknown_before["snapshot"]["budget"]},
            "limitations": [
                "Data-invariant controls; no fresh repair correctness or runtime acceptance",
                "AI-authored implementation and AI-declared reviews; human mastery pending",
                "No live model, paid provider, network call, GPU measurement, or hostile-code isolation",
            ],
        }
        for label, task, kind, subject in (
            ("failed-verification", failed_task, "failed_verification", verification_id),
            ("unknown-dispatch", unknown_task, "unknown_dispatch", dispatch_id),
        ):
            source = store.capture_failure_source("demo-tenant", task["task_id"])
            write_json(output / (label + "-source.json"), source)
            before = store_fingerprint(store)
            evidence = extract_failure_evidence(
                source,
                kind=kind,
                subject_id=subject,
                window={"start_sequence": 1, "end_sequence": source["capture"]["frontier"]},
                source_provenance={
                    "source_id": "trusted-local-demo",
                    "origin": "trusted_local_runtime_store",
                    "source_hashes": source_hashes,
                    "transformations": [],
                    "redactions": [],
                },
                lineage={
                    "family_id": "synthetic-issue-tracker-v1",
                    "source_case_id": label,
                    "parent_evidence_digests": [],
                    "split": "development",
                    "held_out_eligible": False,
                },
                artifact_reader=artifacts.get,
            )
            if evidence.verify()["status"] != "complete":
                raise RuntimeError("demo evidence incomplete: " + str(evidence.read()["reasons"]))
            assert store_fingerprint(store) == before
            predicate, controls = controls_for(evidence)
            controls_ref = artifacts.put_json("demo-tenant", task["task_id"], controls)
            before = store_fingerprint(store)
            case = freeze_regression_case(
                evidence,
                fixture_ref=controls_ref,
                predicate_id=predicate,
                source_hashes=source_hashes,
                artifact_reader=artifacts.get,
            )
            review = record_regression_review(
                case,
                reviewer_id="ai-authored-control-demo",
                reviewer_kind="ai",
                disposition="approved",
                reasons=[
                    "Demonstration of declared AI review format; automated data controls only; independent code review recorded separately"
                ],
                reviewed_at=time.time(),
            )
            assert store_fingerprint(store) == before
            for suffix, record in (("evidence", evidence), ("case", case), ("review", review)):
                (output / f"{label}-{suffix}.json").write_bytes(record.payload)
            write_json(output / (label + "-controls.json"), controls)
            data = evidence.verify()
            packet["observations"].append(
                {
                    "label": label,
                    "evidence_digest": evidence.digest,
                    "case_digest": case.digest,
                    "review_digest": review.digest,
                    "predicate_id": predicate,
                    "predicate_result_label": "predicate satisfied",
                    "known_good": evaluate_regression_fixture(
                        predicate, controls["known_good"], evidence=evidence
                    ),
                    "known_bad": evaluate_regression_fixture(
                        predicate, controls["known_bad"], evidence=evidence
                    ),
                    "case_review_state": case.verify()["review_state"],
                    "reviewer_kind": review.verify()["reviewer_kind"],
                    "review_label": "example declared review",
                    "subject_generation": data["subject"]["generation"],
                    "current_generation": data["scope"]["current_generation"],
                    "accounting": data["accounting"],
                    "fixture_ref": controls_ref,
                    **({"verifier_ref": verifier_ref} if kind == "failed_verification" else {}),
                }
            )
            if kind == "unknown_dispatch":
                packet["unknown_accounting_trace"]["settled_effect_still_unknown"] = source["snapshot"][
                    "budget"
                ]
        write_json(output / "packet.json", packet)
        print(str(output / "packet.json"))
    finally:
        store.close()


if __name__ == "__main__":
    main()
