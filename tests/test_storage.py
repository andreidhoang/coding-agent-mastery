"""Distinguishing authority tests: physical slots, money and effects stay separate."""

import concurrent.futures
import time
from contextlib import contextmanager

import pytest
from service.artifacts import LocalArtifacts, digest_json
from service.contracts import (
    BudgetExceeded,
    CapacityExceeded,
    Conflict,
    Fenced,
    NotFound,
    ResetRequired,
    Unsupported,
    parse_json,
    validate_contract,
)
from service.execution import tree_digest
from service.integration import candidate_manifest
from service.storage import RuntimeStore

BASE = {"solution.py": "def answer(): return 0\n"}
FIXED = {"solution.py": "def answer(): return 1\n"}


def contract(**overrides):
    return {
        "repo_id": "trusted-fixture",
        "base_revision": tree_digest(BASE),
        "requirements": ["answer returns one"],
        "budget_units": 100,
        "execution_deadline": time.time() + 60,
        "review_deadline": time.time() + 120,
        **overrides,
    }


@pytest.fixture
def store(tmp_path):
    instance = RuntimeStore(
        "sqlite:///" + str(tmp_path / "authority.sqlite"),
        LocalArtifacts(tmp_path / "artifacts"),
        service_slot_limit=2,
        tenant_slot_limit=2,
        service_budget_units=100,
        tenant_budget_units=100,
    )
    yield instance
    instance.close()


def task_graph(store, tenant="tenant", nodes=None, **settings):
    task = store.submit(tenant, "submit", contract(**settings))
    store.set_graph(
        tenant,
        task["task_id"],
        task["generation"],
        nodes or [{"node_id": "patch", "allowed_paths": ["solution.py"]}],
    )
    return task


def claim(store, task, node="patch", claim_id="claim", units=40):
    return store.claim(task["tenant_id"], task["task_id"], node, claim_id, units, 30)


def manifest(grant, files=FIXED, inputs=None):
    result = candidate_manifest(
        dict(BASE), dict(files), ["solution.py"], grant["owner"], ["answer returns one"], inputs
    )
    if "base_files" not in result:
        result["base_files"] = BASE
        result["manifest_digest"] = digest_json({k: v for k, v in result.items() if k != "manifest_digest"})
    return result


def complete_head(store, task):
    grant = claim(store, task)
    candidate = store.accept_candidate(grant["owner"], manifest(grant))
    integrated = store.integrate(
        task["tenant_id"], task["task_id"], 1, [candidate["candidate_id"]], 0, candidate["manifest"]
    )
    return grant, integrated


def test_submission_frozen_idempotence_and_tenant_isolation(store):
    body = contract()
    task = store.submit("tenant", "submit", body)
    body["requirements"].append("mutable request edit")
    assert store.get_task("tenant", task["task_id"])["contract"]["requirements"] == ["answer returns one"]
    body["requirements"].pop()
    assert store.submit("tenant", "submit", body)["task_id"] == task["task_id"]
    with pytest.raises(Conflict):
        store.submit("tenant", "submit", {**body, "budget_units": 99})
    for method in (store.get_task, store.snapshot, store.events):
        with pytest.raises(NotFound):
            method("another", task["task_id"])
    # Idempotent retry survives draining and omitted defaults do not get recomputed.
    store.set_admission(False)
    assert store.submit("tenant", "submit", body)["task_id"] == task["task_id"]
    with pytest.raises(CapacityExceeded):
        store.submit("tenant", "new", body)


def test_strict_contract_json_and_graph_guards(store):
    for value in (True, -1, 1.5):
        with pytest.raises(ValueError):
            validate_contract(contract(budget_units=value))
    with pytest.raises(ValueError):
        parse_json('{"budget":1,"budget":2}')
    with pytest.raises(ValueError):
        parse_json('{"budget":NaN}')
    with pytest.raises(Unsupported):
        validate_contract(contract(patch_slot_limit=4))
    task = store.submit("tenant", "submit", contract(max_nodes=2))
    for graph in (
        [{"node_id": "a", "dependencies": ["b"]}, {"node_id": "b", "dependencies": ["a"]}],
        [{"node_id": "a", "dependencies": ["missing"]}],
    ):
        with pytest.raises(Conflict):
            store.set_graph("tenant", task["task_id"], 1, graph)
    with pytest.raises(CapacityExceeded):
        store.set_graph("tenant", task["task_id"], 1, [{"node_id": x} for x in "abc"])


def test_two_schedulers_one_node_and_idempotent_claim(store):
    task = task_graph(store)

    def compete(index):
        try:
            return claim(store, task, claim_id=f"claim-{index}")
        except (Fenced, CapacityExceeded) as exc:
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, range(2)))
    granted = [x for x in results if isinstance(x, dict)]
    assert len(granted) == 1
    grant = granted[0]
    same = store.claim("tenant", task["task_id"], "patch", f"claim-{results.index(grant)}", 40, 30)
    assert same == grant
    with pytest.raises(Conflict):
        store.claim("tenant", task["task_id"], "patch", f"claim-{results.index(grant)}", 41, 30)
    assert store.get_task("tenant", task["task_id"])["budget"] == {"spent": 0, "reserved": 40, "limit": 100}


def test_atomic_last_slot_and_shared_budget(tmp_path):
    store = RuntimeStore(
        "sqlite:///" + str(tmp_path / "race.sqlite"),
        service_slot_limit=1,
        tenant_slot_limit=1,
        service_budget_units=50,
        tenant_budget_units=50,
    )
    task = task_graph(store, nodes=[{"node_id": "a"}, {"node_id": "b"}])

    def compete(node):
        try:
            return claim(store, task, node, node, 40)
        except (CapacityExceeded, BudgetExceeded) as exc:
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, ["a", "b"]))
    assert len([x for x in results if isinstance(x, dict)]) == 1
    assert store.get_task("tenant", task["task_id"])["physical_slots"] == 1
    store.close()


def test_budget_race_across_tasks_without_capacity_bottleneck(store):
    first = task_graph(store)
    second = store.submit("tenant", "second", contract())
    store.set_graph("tenant", second["task_id"], 1, [{"node_id": "patch"}])

    def compete(task):
        try:
            return claim(store, task, claim_id=task["task_id"], units=60)
        except BudgetExceeded as exc:
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, [first, second]))
    assert len([x for x in results if isinstance(x, dict)]) == 1
    assert sum(store.get_task("tenant", t["task_id"])["budget"]["reserved"] for t in (first, second)) == 60


def test_unknown_effect_keeps_liability_and_blocks_blind_replacement(store):
    task = task_graph(store)
    grant = claim(store, task)
    dispatch = store.begin_dispatch(grant["owner"], "edit", "dispatch", "tool.edit", "a" * 64, 12)
    assert dispatch["duplicate"] is False
    assert (
        store.begin_dispatch(grant["owner"], "edit", "dispatch", "tool.edit", "a" * 64, 12)["duplicate"]
        is True
    )
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 40  # transfer, no double charge
    store.finish_dispatch("tenant", "dispatch", "uncertain", "unknown")
    store.retire_sandbox("tenant", grant["sandbox_id"], {"supervisor": "fixture", "exit_observed": True})
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 12
    with pytest.raises(Fenced):
        claim(store, task, claim_id="replacement")
    store.finish_dispatch("tenant", "dispatch", "reconciled", "succeeded", 9, {"effect": "reconstructed"})
    assert store.get_task("tenant", task["task_id"])["budget"] == {"spent": 9, "reserved": 0, "limit": 100}
    replacement = claim(store, task, claim_id="replacement")
    assert replacement["node_epoch"] == 2
    with pytest.raises(Fenced):
        store.accept_candidate(grant["owner"], manifest(grant))
    with pytest.raises(Fenced):
        store.claim("tenant", task["task_id"], "patch", "claim", 40, 30)


def test_cancel_preserves_unknown_and_late_settlement_once(store):
    task = task_graph(store)
    grant = claim(store, task)
    store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 12)
    store.cancel("tenant", task["task_id"], "cancel")
    store.finish_dispatch("tenant", "dispatch", "lost-response", "unknown")
    assert store.get_task("tenant", task["task_id"])["physical_slots"] == 1
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 40
    store.retire_sandbox("tenant", grant["sandbox_id"], {"exit_observed": True})
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 12
    receipt = store.finish_dispatch("tenant", "dispatch", "bill", "succeeded", 9)
    assert store.finish_dispatch("tenant", "dispatch", "bill", "succeeded", 9) == receipt
    with pytest.raises(Conflict):
        store.finish_dispatch("tenant", "dispatch", "bill", "succeeded", 10)
    assert store.get_task("tenant", task["task_id"])["budget"] == {"spent": 9, "reserved": 0, "limit": 100}
    assert store.get_task("tenant", task["task_id"])["generation"] == 2
    with pytest.raises(Fenced):
        store.accept_candidate(grant["owner"], manifest(grant))


def test_overbound_charge_is_recorded_and_contains_service(store):
    task = task_graph(store)
    grant = claim(store, task)
    store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 12)
    with pytest.raises(BudgetExceeded):
        store.finish_dispatch("tenant", "dispatch", "bill", "succeeded", 19)
    state = store.snapshot("tenant", task["task_id"])
    assert state["quarantined"]
    assert state["budget"]["spent"] == 19
    assert state["dispatches"][0]["bound_violation"] is True
    with pytest.raises(Fenced):
        store.heartbeat(grant["owner"], 30)


def test_database_deadline_is_not_worker_timestamp(store):
    task = task_graph(store, execution_deadline=time.time() + 0.2)
    grant = claim(store, task)
    time.sleep(0.25)
    with pytest.raises(Fenced):
        store.accept_candidate(grant["owner"], {**manifest(grant), "worker_finished_at": task["created_at"]})
    with pytest.raises(Fenced):
        store.heartbeat(grant["owner"], 30)
    assert store.snapshot("tenant", task["task_id"])["candidates"] == []


def test_sibling_epochs_and_dependency_versions(store):
    task = task_graph(
        store, nodes=[{"node_id": "a"}, {"node_id": "b"}, {"node_id": "c", "dependencies": ["a"]}]
    )
    a = claim(store, task, "a", "a", 10)
    b = claim(store, task, "b", "b", 10)
    store.heartbeat(a["owner"], 30)
    with pytest.raises(Fenced):
        claim(store, task, "c", "c", 10)
    ca = store.accept_candidate(a["owner"], manifest(a))
    store.retire_sandbox("tenant", a["sandbox_id"], {"exit_observed": True})
    store.heartbeat(b["owner"], 30)  # sibling completion leaves this owner valid
    c = claim(store, task, "c", "c", 10)
    with pytest.raises(Fenced):
        store.accept_candidate(c["owner"], manifest(c, inputs=["stale-input"]))
    cc = store.accept_candidate(c["owner"], manifest(c, inputs=[ca["candidate_id"]]))
    assert cc["dependency_versions"] == {"a": ca["candidate_id"]}


def test_exact_tree_verifier_review_and_head_cas(store):
    task = task_graph(store)
    grant, head = complete_head(store, task)
    with pytest.raises(Conflict):
        store.integrate("tenant", task["task_id"], 1, head["parent_candidate_ids"], 0, head["manifest"])
    with pytest.raises(Conflict):
        store.record_verification(
            "tenant",
            task["task_id"],
            1,
            head["candidate_id"],
            "a" * 64,
            task["contract"]["grader_digest"],
            task["contract"]["environment_digest"],
            "pass",
            {"supervisor": "trusted"},
        )
    verification = store.record_verification(
        "tenant",
        task["task_id"],
        1,
        head["candidate_id"],
        head["tree_digest"],
        task["contract"]["grader_digest"],
        task["contract"]["environment_digest"],
        "pass",
        {"supervisor": "trusted"},
    )
    review = store.publish_review(
        "tenant", task["task_id"], 1, head["candidate_id"], verification["verification_id"], 1
    )
    assert (
        store.publish_review(
            "tenant", task["task_id"], 1, head["candidate_id"], verification["verification_id"], 1
        )
        == review
    )
    decision = store.record_review(
        "tenant", task["task_id"], review["review_id"], "human", "accepted", "review-key"
    )
    assert (
        store.record_review("tenant", task["task_id"], review["review_id"], "human", "accepted", "review-key")
        == decision
    )
    with pytest.raises(Fenced):
        store.heartbeat(grant["owner"], 30)


def test_new_head_needs_new_verification(store):
    task = task_graph(store)
    _, head = complete_head(store, task)
    verification = store.record_verification(
        "tenant",
        task["task_id"],
        1,
        head["candidate_id"],
        head["tree_digest"],
        task["contract"]["grader_digest"],
        task["contract"]["environment_digest"],
        "pass",
        {"supervisor": "trusted"},
    )
    next_head = store.integrate(
        "tenant", task["task_id"], 1, head["parent_candidate_ids"], 1, head["manifest"]
    )
    with pytest.raises(Fenced):
        store.publish_review(
            "tenant", task["task_id"], 1, next_head["candidate_id"], verification["verification_id"], 2
        )


def test_draining_restore_quarantine_old_cursor_and_reconciliation(store):
    task = task_graph(store)
    grant = claim(store, task)
    page = store.events("tenant", task["task_id"])
    # Every event can independently resume; not every row has page-end cursor.
    first = page["events"][0]
    assert (
        store.events("tenant", task["task_id"], first["cursor"])["events"][0]["sequence"]
        == first["sequence"] + 1
    )
    store.set_admission(False)
    store.heartbeat(grant["owner"], 30)
    store.quarantine_restore("fresh-incarnation", {"backup_id": "backup-one", "sequence": 1})
    with pytest.raises(ResetRequired) as reset:
        store.events("tenant", task["task_id"], page["cursor"])
    assert reset.value.snapshot["quarantined"] is True
    with pytest.raises(Fenced):
        store.heartbeat(grant["owner"], 30)
    with pytest.raises(Fenced):
        store.resume_after_reconciliation({"reconciled": True})
    evidence = {
        "actor_fencing": {"controller": "retired"},
        "effect_reconciliation": {"provider": "none"},
        "recovery_frontier": {"backup_id": "backup-one", "sequence": 1},
    }
    with pytest.raises(Fenced):
        store.resume_after_reconciliation(evidence)
    store.retire_sandbox("tenant", grant["sandbox_id"], {"exit_observed": True})
    store.resume_after_reconciliation(evidence)
    with pytest.raises(Fenced):
        claim(store, task, claim_id="stale-controller")
    fresh = RuntimeStore(str(store.engine.url), store.artifact_store)
    replacement = claim(fresh, task, claim_id="restored")
    fresh.close()
    assert replacement["service_incarnation"] == "fresh-incarnation"
    with pytest.raises(Fenced):
        store.accept_candidate(grant["owner"], manifest(grant))


def test_artifact_integrity_binding_and_no_external_rpc_under_lock(store, monkeypatch):
    task = task_graph(store)
    grant = claim(store, task)
    candidate = manifest(grant)
    ref = store.artifact_store.put_json("tenant", task["task_id"], candidate)
    with pytest.raises(NotFound):
        store.authorize_artifact("tenant", task["task_id"], ref["digest"])
    locked = False
    original_tx = store._tx
    original_get = store.artifact_store.get

    @contextmanager
    def tracked():
        nonlocal locked
        with original_tx() as value:
            locked = True
            try:
                yield value
            finally:
                locked = False

    def get(tenant, task_id, blob):
        assert not locked, "artifact RPC occurred inside authority transaction"
        return original_get(tenant, task_id, blob)

    monkeypatch.setattr(store, "_tx", tracked)
    monkeypatch.setattr(store.artifact_store, "get", get)
    accepted = store.accept_candidate(grant["owner"], {**candidate, "artifact_ref": ref})
    assert store.authorize_artifact("tenant", task["task_id"], ref["digest"]) == ref
    assert accepted["manifest"]["artifact_ref"] == ref
    with pytest.raises(NotFound):
        store.authorize_artifact("other", task["task_id"], ref["digest"])


def test_outbox_reopens_and_checkpoint_preserves_unknown(store):
    task = task_graph(store)
    grant = claim(store, task)
    store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 12)
    cp = store.checkpoint(
        grant["owner"],
        {"workspace": BASE, "provider_artifacts": [{"opaque": "kept"}], "pending_calls": ["call-1"]},
    )
    assert cp["pending_dispatches"][0]["dispatch_id"] == "dispatch"
    assert cp["dispatch_frontier"] == ["dispatch"]
    commands = store.list_outbox()
    reopened = RuntimeStore(str(store.engine.url))
    assert {x["command_id"] for x in reopened.list_outbox()} == {x["command_id"] for x in commands}
    reopened.ack_outbox(commands[0]["command_id"])
    reopened.ack_outbox(commands[0]["command_id"])
    assert commands[0]["command_id"] not in {x["command_id"] for x in store.list_outbox()}
    reopened.close()


def test_bill_can_settle_before_effect_is_reconciled_without_second_charge(store):
    task = task_graph(store)
    grant = claim(store, task)
    store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 12)
    store.finish_dispatch("tenant", "dispatch", "bill-before-effect", "unknown", 9)
    assert store.get_task("tenant", task["task_id"])["budget"]["spent"] == 9
    result = store.finish_dispatch(
        "tenant", "dispatch", "reconstruct-effect", "succeeded", result_ref={"reconstructed": True}
    )
    assert result["billing_state"] == "settled" and result["actual_units"] == 9
    assert result["effect_state"] == "succeeded"
    store.finish_dispatch(
        "tenant", "dispatch", "reconstruct-effect", "succeeded", result_ref={"reconstructed": True}
    )
    assert store.get_task("tenant", task["task_id"])["budget"]["spent"] == 9
    with pytest.raises(Conflict):
        store.finish_dispatch("tenant", "dispatch", "another-charge", "succeeded", 10)


def test_lying_changed_paths_and_unbound_baseline_rejected(store):
    task = task_graph(store)
    grant = claim(store, task)
    forged = manifest(grant)
    forged["files"]["protected.py"] = "grader overridden"
    forged["tree_digest"] = tree_digest(forged["files"])
    forged["manifest_digest"] = digest_json({k: v for k, v in forged.items() if k != "manifest_digest"})
    with pytest.raises(Conflict, match="exact delta"):
        store.accept_candidate(grant["owner"], forged)
    forged["changed_paths"] = ["protected.py", "solution.py"]
    forged["manifest_digest"] = digest_json({k: v for k, v in forged.items() if k != "manifest_digest"})
    with pytest.raises(Fenced, match="outside"):
        store.accept_candidate(grant["owner"], forged)
    forged["base_files"] = {"solution.py": "different baseline"}
    forged["manifest_digest"] = digest_json({k: v for k, v in forged.items() if k != "manifest_digest"})
    with pytest.raises(Conflict, match="base digest"):
        store.accept_candidate(grant["owner"], forged)
    assert store.snapshot("tenant", task["task_id"])["candidates"] == []


def test_final_acceptance_rechecks_database_time_after_expensive_validation(store, monkeypatch):
    task = task_graph(store, execution_deadline=time.time() + 0.2)
    grant = claim(store, task)
    original = store._manifest

    def slow_validate(*args):
        result = original(*args)
        time.sleep(0.25)
        return result

    monkeypatch.setattr(store, "_manifest", slow_validate)
    with pytest.raises(Fenced, match="deadline"):
        store.accept_candidate(grant["owner"], manifest(grant))
    assert store.snapshot("tenant", task["task_id"])["candidates"] == []


def test_restore_fences_old_integrator_verifier_and_publisher(store):
    task = task_graph(store)
    grant, head = complete_head(store, task)
    store.quarantine_restore("fresh-controller", {"backup": "one"})
    store.retire_sandbox("tenant", grant["sandbox_id"], {"exit_observed": True})
    store.resume_after_reconciliation(
        {
            "actor_fencing": {"controllers": "retired"},
            "effect_reconciliation": {"provider": "no effects"},
            "recovery_frontier": {"backup": "one"},
        }
    )
    with pytest.raises(Fenced, match="control-plane"):
        store.integrate("tenant", task["task_id"], 1, head["parent_candidate_ids"], 1, head["manifest"])
    args = (
        "tenant",
        task["task_id"],
        1,
        head["candidate_id"],
        head["tree_digest"],
        task["contract"]["grader_digest"],
        task["contract"]["environment_digest"],
        "pass",
        {"supervisor": "trusted"},
    )
    with pytest.raises(Fenced, match="control-plane"):
        store.record_verification(*args)
    fresh = RuntimeStore(str(store.engine.url), store.artifact_store)
    verification = fresh.record_verification(*args)
    with pytest.raises(Fenced, match="control-plane"):
        store.publish_review(
            "tenant", task["task_id"], 1, head["candidate_id"], verification["verification_id"], 1
        )
    review = fresh.publish_review(
        "tenant", task["task_id"], 1, head["candidate_id"], verification["verification_id"], 1
    )
    assert review["status"] == "pending"
    fresh.close()


def test_auxiliary_environment_counts_aggregate_slots_and_retains_unknown(store):
    task = task_graph(store, nodes=[{"node_id": "a"}, {"node_id": "b"}], patch_slot_limit=1)
    worker = claim(store, task, "a", "worker", 10)
    verifier = store.reserve_environment("tenant", task["task_id"], 1, "verifier", "verify-one")
    assert verifier["duplicate"] is False
    assert verifier["attempt_id"] is None and verifier["kind"] == "verifier"
    assert (
        store.reserve_environment("tenant", task["task_id"], 1, "verifier", "verify-one")["duplicate"] is True
    )
    with pytest.raises(CapacityExceeded):
        store.reserve_environment("tenant", task["task_id"], 1, "integrator", "integrate-one")
    with pytest.raises(CapacityExceeded):
        claim(store, task, "b", "worker-two", 10)
    # Worker lease/cancellation does not release auxiliary physical slot.
    store.cancel("tenant", task["task_id"], "cancel")
    store.retire_sandbox("tenant", worker["sandbox_id"], {"exit_observed": True})
    assert store.get_task("tenant", task["task_id"])["physical_slots"] == 1
    store.retire_sandbox(
        "tenant", verifier["sandbox_id"], {"supervisor": "trusted", "container_removed": True}
    )
    store.retire_sandbox(
        "tenant", verifier["sandbox_id"], {"supervisor": "trusted", "container_removed": True}
    )
    assert store.get_task("tenant", task["task_id"])["physical_slots"] == 0


def test_event_cursor_tamper_and_cross_task_not_authorized(store):
    task = task_graph(store)
    cursor = store.events("tenant", task["task_id"])["cursor"]
    second = store.submit("tenant", "second", contract())
    with pytest.raises(NotFound):
        store.events("tenant", second["task_id"], cursor)
    with pytest.raises(Conflict):
        store.events("tenant", task["task_id"], cursor[:-8] + "aaaaaaaa")


def test_terminal_failure_revokes_authority_preserves_physical_and_money(store):
    task = task_graph(store)
    grant = claim(store, task)
    store.begin_dispatch(grant["owner"], "model", "dispatch", "model.generate", "a" * 64, 12)
    store.finish_dispatch("tenant", "dispatch", "lost-response", "unknown")
    failed = store.fail_execution(
        "tenant",
        task["task_id"],
        1,
        "effect_unknown",
        {"supervisor": "trusted", "uncertain": "unreconstructible"},
    )
    assert failed["execution_state"] == "failed" and failed["generation"] == 2
    assert store.get_task("tenant", task["task_id"])["physical_slots"] == 1
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 40
    with pytest.raises(Fenced):
        store.accept_candidate(grant["owner"], manifest(grant))
    store.retire_sandbox("tenant", grant["sandbox_id"], {"exit_observed": True})
    assert store.get_task("tenant", task["task_id"])["budget"]["reserved"] == 12
    store.finish_dispatch("tenant", "dispatch", "late-bill", "succeeded", 9)
    assert store.get_task("tenant", task["task_id"])["execution_state"] == "failed"
    assert store.get_task("tenant", task["task_id"])["budget"] == {"spent": 9, "reserved": 0, "limit": 100}


def test_deadline_failure_is_revocation_only_after_db_cutoff(store):
    task = task_graph(store, execution_deadline=time.time() + 0.2)
    grant = claim(store, task)
    with pytest.raises(Conflict):
        store.fail_execution("tenant", task["task_id"], 1, "deadline_exceeded", {"timer": "trusted"})
    time.sleep(0.25)
    result = store.fail_execution("tenant", task["task_id"], 1, "deadline_exceeded", {"timer": "trusted"})
    assert result["failure"]["reason"] == "deadline_exceeded"
    with pytest.raises(Fenced):
        store.heartbeat(grant["owner"], 30)
