"""Trusted local failure fixtures shared by adapter tests and its bounded demo."""

from __future__ import annotations

import copy
import os
import time
import uuid

import pytest
import sqlalchemy as sa

from service.artifacts import LocalArtifacts, canonical_bytes
from service.execution import tree_digest
from service.integration import candidate_manifest
from service.storage import RuntimeStore, TABLES, authority, event_rows
from service.verification import FixtureVerifier
from workloads.registry import ROOT, TARGET_FILES, list_tasks

PROVENANCE = {
    "source_id": "trusted-local-test",
    "origin": "trusted_local_runtime_store",
    "source_hashes": {"fixture": "a" * 64},
    "transformations": [],
    "redactions": [],
}
LINEAGE = {
    "family_id": "synthetic-issue-tracker-v1",
    "source_case_id": "declared-local-control",
    "parent_evidence_digests": [],
    "split": "development",
    "held_out_eligible": False,
}


@pytest.fixture
def failure_store(tmp_path):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore(
        "sqlite:///" + str(tmp_path / "runtime.sqlite"),
        artifacts,
        service_slot_limit=4,
        tenant_slot_limit=4,
        service_budget_units=1000,
        tenant_budget_units=1000,
    )
    with store.engine.connect() as c:
        c.exec_driver_sql("PRAGMA journal_mode=WAL")
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def failure_postgres_store(tmp_path):
    url = os.environ.get("CAM_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("CAM_TEST_POSTGRES_URL is not configured")
    namespace = "failure_test_" + uuid.uuid4().hex
    admin = sa.create_engine(url)
    with admin.begin() as c:
        c.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    parsed = sa.engine.make_url(url).update_query_dict({"options": "-csearch_path=" + namespace})
    store = RuntimeStore(
        parsed.render_as_string(hide_password=False),
        LocalArtifacts(tmp_path / "artifacts"),
        service_slot_limit=4,
        tenant_slot_limit=4,
        service_budget_units=1000,
        tenant_budget_units=1000,
    )
    try:
        yield store
    finally:
        store.close()
        with admin.begin() as c:
            c.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


def make_task(store, *, key="submission", nodes=("patch",), base=None, grader=None, environment=None):
    base = base or {"solution.py": "def answer(): return 0\n"}
    task = store.submit(
        "tenant",
        key,
        {
            "repo_id": "synthetic-issue-tracker-v1",
            "base_revision": tree_digest(base),
            "requirements": ["trusted local control"],
            "budget_units": 100,
            "execution_deadline": time.time() + 600,
            "review_deadline": time.time() + 1200,
            **({"grader_digest": grader} if grader else {}),
            **({"environment_digest": environment} if environment else {}),
        },
    )
    store.set_graph(
        "tenant",
        task["task_id"],
        task["generation"],
        [{"node_id": node, "allowed_paths": list(base)} for node in nodes],
    )
    return task


def failed_verification(store):
    definition = list_tasks(split="calibration")[0]
    base = {name: (definition.baseline_path / name).read_text() for name in TARGET_FILES}
    incorrect = {
        name: (ROOT / "oracle" / "incorrect" / definition.baseline_id / name).read_text()
        for name in TARGET_FILES
    }
    verifier = FixtureVerifier()
    result = verifier.verify(incorrect, definition)
    assert result["passed"] is False
    task = make_task(
        store, base=base, grader=result["grader_digest"], environment=result["environment_digest"]
    )
    grant = store.claim("tenant", task["task_id"], "patch", "claim", 40, 60)
    manifest = candidate_manifest(
        base, incorrect, list(TARGET_FILES), grant["owner"], task["contract"]["requirements"]
    )
    candidate = store.accept_candidate(grant["owner"], manifest)
    head = store.integrate(
        "tenant", task["task_id"], 1, [candidate["candidate_id"]], 0, candidate["manifest"]
    )
    ref = store.artifact_store.put_json("tenant", task["task_id"], result)
    verification = store.record_verification(
        "tenant",
        task["task_id"],
        1,
        head["candidate_id"],
        head["tree_digest"],
        result["grader_digest"],
        result["environment_digest"],
        "fail",
        ref,
    )
    store.fail_execution("tenant", task["task_id"], 1, "candidate_failed", ref)
    return task, verification, ref, result


def unknown_dispatch(store, *, settled=False, all_nodes=False, result_ref=None):
    nodes = ("parent", "child", "summary") if all_nodes else ("patch",)
    task = make_task(store, nodes=nodes)
    selected = None
    for node, units in zip(nodes, (10, 7, 3) if all_nodes else (9,)):
        grant = store.claim("tenant", task["task_id"], node, "claim-" + node, 40, 60)
        dispatch_id = "dispatch-" + node
        store.begin_dispatch(grant["owner"], "model-" + node, dispatch_id, "model.generate", "b" * 64, 12)
        receipt = "receipt-" + node
        state = "unknown" if node == nodes[-1] else "succeeded"
        actual = units if settled or all_nodes else None
        store.finish_dispatch("tenant", dispatch_id, receipt, state, actual, result_ref)
        # Exact retry is an idempotent store operation, not an invented duplicate ledger entry.
        store.finish_dispatch("tenant", dispatch_id, receipt, state, actual, result_ref)
        store.retire_sandbox("tenant", grant["sandbox_id"], {"supervisor": "trusted", "exit_observed": True})
        selected = dispatch_id
    return task, selected


def capture(store, task):
    return store.capture_failure_source("tenant", task["task_id"])


def extract(store, task, kind, subject_id, *, source=None, window=None, **kwargs):
    from evals.evidence import extract_failure_evidence

    source = source if source is not None else capture(store, task)
    return extract_failure_evidence(
        source,
        kind=kind,
        subject_id=subject_id,
        window=window or {"start_sequence": 1, "end_sequence": source["capture"]["frontier"]},
        source_provenance=copy.deepcopy(PROVENANCE),
        lineage=copy.deepcopy(LINEAGE),
        artifact_reader=kwargs.pop("artifact_reader", store.artifact_store.get),
        **kwargs,
    )


def refresh_metadata(source):
    """Refresh truthful size/count envelope after an adversarial semantic edit."""
    source["capture"]["source_bytes"] = len(
        canonical_bytes({k: source[k] for k in ("snapshot", "receipts", "submissions", "events")})
    )
    counts = source["capture"]["table_counts"]
    for name in counts:
        counts[name] = 1 if name == "tasks" else len(source.get(name, source["snapshot"].get(name, [])))
    source["capture"]["event_count"] = len(source["events"])
    return source


def fingerprint(store):
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
        str(path.relative_to(store.artifact_store.root)): path.read_bytes()
        for path in store.artifact_store.root.rglob("*")
        if path.is_file()
    }
    return data, artifacts


def fixtures_for(evidence):
    data = evidence.verify()
    subject, identities, accounting = data["subject"], data["identities"], data["accounting"]
    if data["kind"] == "failed_verification":
        predicate = "verification.exact_binding.v1"
        good = {
            key: identities[key]
            for key in (
                "contract_digest",
                "base_revision",
                "candidate_id",
                "tree_digest",
                "grader_digest",
                "environment_digest",
            )
        }
        good.update({key: subject[key] for key in ("verification_id", "generation", "outcome")})
        bad = {**good, "tree_digest": "f" * 64}
    else:
        predicate = "dispatch.unknown_accounting.v1"
        dispatch = next(
            row for row in accounting["dispatches"] if row["dispatch_id"] == subject["dispatch_id"]
        )
        good = {
            key: dispatch[key]
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
                key: accounting[key]
                for key in (
                    "spent_units",
                    "reserved_units",
                    "attempt_allowance_units",
                    "unsettled_bound_units",
                )
            }
        )
        bad = {**good, "reserved_units": good["reserved_units"] + 1}
    return predicate, {
        "schema": 1,
        "evidence_digest": evidence.digest,
        "predicate_id": predicate,
        "known_good": good,
        "known_bad": bad,
    }
