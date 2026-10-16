"""Independent environment schema, transaction, authority and accounting gates."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import threading
import uuid

import pytest
import sqlalchemy as sa

from service.storage import RuntimeStore
from test_environment_recovery import (
    CID, FROZEN_POLICY, REJECT, case, canonical, digest, instance, journal, reconcile, snapshot, started,
)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def backend(request):
    if request.param == "sqlite":
        yield None
        return
    if not os.environ.get("CAM_TEST_POSTGRES_URL"):
        pytest.skip("CAM_TEST_POSTGRES_URL not configured")
    admin = sa.create_engine(os.environ["CAM_TEST_POSTGRES_URL"])
    namespace = "environment_recovery_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    url = sa.engine.make_url(os.environ["CAM_TEST_POSTGRES_URL"]).update_query_dict(
        {"options": "-csearch_path=" + namespace})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


def observe(c, kind, status, *, cid=CID, diagnostic="", **changes):
    j = journal(c)
    row = j["instances"][-1]
    value = {"schema": 1, "profile": "docker_environment_observation_v1", "kind": kind,
        "backend": j["backend"], "intent_id": row["intent_id"], "ordinal": row["ordinal"],
        "name": row["name"], "creation_nonce": row["creation_nonce"], "launch_digest": digest(row["launch"]),
        "container_id": cid, "status": status, "diagnostic": diagnostic, **changes}
    value["operation_id"] = digest(value)
    ref = c.artifacts.put_json(c.task["tenant_id"], c.task["task_id"], value)
    return row, value, ref, j["revision"]


def bind(c):
    row, value, ref, revision = observe(c, "create", "bound")
    return c.store.bind_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"],
        row["intent_id"], ref, expected_revision=revision)


def retire_instance(c):
    row, value, ref, revision = observe(c, "retirement", "absent")
    return c.store.record_environment_retirement(c.task["tenant_id"], c.reservation["sandbox_id"],
        row["intent_id"], ref, expected_revision=revision)


@pytest.mark.parametrize("field,value", [("ordinal", True), ("ordinal", -1), ("ordinal", 1),
    ("max_instances", True), ("max_instances", 0), ("max_instances", 33),
    ("source", {"schema": 1}), ("backend", {"kind": "docker_remote"}), ("launch", {"network": "host"})])
def test_E08_closed_admission_refuses_before_effect_or_partial_event(tmp_path, backend, field, value):
    c = case(tmp_path, url=backend)
    request = {"source": c.source, "backend": c.backend.backend, "max_instances": 1, "ordinal": 0, "launch": c.launch}
    request[field] = value
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.store.begin_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"], **request)
    assert snapshot(c) == before and not c.fake.effects


@pytest.mark.parametrize("field,value", [("generation", True), ("service_incarnation", "a" * 129),
    ("service_incarnation", "日本"), ("purpose", "model_tool"), ("tree_digest", "not-a-digest"),
    ("grader_digest", "f" * 64), ("environment_digest", "e" * 64)])
def test_E05_E08_source_identity_refuses_before_authority_write(tmp_path, backend, field, value):
    c = case(tmp_path, url=backend)
    c.source[field] = value
    before = snapshot(c)
    with pytest.raises(REJECT):
        instance(c)
    assert snapshot(c) == before and not c.fake.effects


@pytest.mark.parametrize("field,value", [("memory_mb", True), ("memory_mb", 31), ("cpus", True),
    ("cpus", float("inf")), ("pids", 257), ("disk_mb", 129), ("timeout_seconds", 0),
    ("policy_digest", "f" * 64), ("image", "mutable:latest"), ("extra", "unapproved")])
def test_E08_launch_policy_is_closed_and_bounded(tmp_path, backend, field, value):
    c = case(tmp_path, url=backend)
    before = snapshot(c)
    with pytest.raises(REJECT):
        instance(c, **{field: value})
    assert snapshot(c) == before and not c.fake.effects


def test_E01_changed_same_ordinal_intent_conflicts_with_original_nonce(tmp_path, backend):
    c = case(tmp_path, url=backend)
    assert c.launch["policy_digest"] == digest(FROZEN_POLICY)
    instance(c)
    saved, before = deepcopy(journal(c)), snapshot(c)
    with pytest.raises(REJECT):
        instance(c, memory_mb=256)
    assert journal(c) == saved and snapshot(c) == before and not c.fake.effects


def test_E11_artifacts_and_docker_never_execute_inside_authority_transaction(tmp_path, monkeypatch, backend):
    c = case(tmp_path, url=backend)
    depth = 0
    original_tx = c.store._tx
    @contextmanager
    def tracked():
        nonlocal depth
        with original_tx() as active:
            depth += 1
            try:
                yield active
            finally:
                depth -= 1
    monkeypatch.setattr(c.store, "_tx", tracked)
    for name in ("get", "get_json", "put", "put_json", "check_ref"):
        if hasattr(c.artifacts, name):
            original = getattr(c.artifacts, name)
            def guard(*a, _original=original, **k):
                assert depth == 0, "Artifact I/O occurred under the authority transaction"
                return _original(*a, **k)
            monkeypatch.setattr(c.artifacts, name, guard)
    original_runner = c.backend.runner
    def runner(*a, **k):
        assert depth == 0, "Docker I/O occurred under the authority transaction"
        return original_runner(*a, **k)
    c.backend.runner = runner
    sandbox = started(c)
    assert sandbox.close()["retired"] is True
    assert reconcile(c)["status"] == "retired" and depth == 0


def test_E11_identical_bind_and_terminal_observation_are_read_only(tmp_path, backend):
    c = case(tmp_path, url=backend)
    instance(c)
    row, value, ref, rev = observe(c, "create", "bound")
    first = c.store.bind_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"], ref, expected_revision=rev)
    before = snapshot(c)
    second = c.store.bind_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"], ref, expected_revision=rev)
    assert first["duplicate"] is False and second["duplicate"] is True
    assert {k: v for k, v in first.items() if k != "duplicate"} == {k: v for k, v in second.items() if k != "duplicate"}
    assert snapshot(c) == before
    row, value, ref, rev = observe(c, "retirement", "absent")
    first = c.store.record_environment_retirement(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"], ref, expected_revision=rev)
    before = snapshot(c)
    second = c.store.record_environment_retirement(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"], ref, expected_revision=rev)
    assert first["duplicate"] is False and second["duplicate"] is True
    assert {k: v for k, v in first.items() if k != "duplicate"} == {k: v for k, v in second.items() if k != "duplicate"}
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["nonce", "id", "launch", "scope", "unknown", "bool_version", "bool_ordinal", "diagnostic", "size", "operation"])
def test_E08_forged_observation_rejects_without_partial_binding(tmp_path, backend, fault):
    c = case(tmp_path, url=backend)
    instance(c)
    row, value, ref, rev = observe(c, "create", "bound")
    if fault == "nonce":
        value["creation_nonce"] = "f" * 32
    elif fault == "id":
        value["container_id"] = "too-short"
    elif fault == "launch":
        value["launch_digest"] = "d" * 64
    elif fault == "unknown":
        value["trusted"] = True
    elif fault == "bool_version":
        value["schema"] = True
    elif fault == "bool_ordinal":
        value["ordinal"] = False
    elif fault == "diagnostic":
        value["diagnostic"] = "x" * 1025
    elif fault == "size":
        value["diagnostic"] = "x" * 16384
    elif fault == "operation":
        value["operation_id"] = "f" * 64
    if fault != "operation":
        value["operation_id"] = digest({k: v for k, v in value.items() if k != "operation_id"})
    ref = c.artifacts.put_json(c.task["tenant_id"], c.task["task_id"] if fault != "scope" else "foreign-task", value)
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.store.bind_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"], ref, expected_revision=rev)
    assert snapshot(c) == before


def test_E08_1024_diagnostic_is_exact_boundary_and_1025_rejects(tmp_path, backend):
    c = case(tmp_path, url=backend)
    instance(c)
    row, value, ref, rev = observe(c, "retirement", "unresolved", cid=None, diagnostic="x" * 1024)
    c.store.record_environment_retirement(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"], ref, expected_revision=rev)
    assert journal(c)["instances"][0]["state"] == "create_intent"
    row, value, ref, rev = observe(c, "retirement", "unresolved", cid=None, diagnostic="x" * 1025)
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.store.record_environment_retirement(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"], ref, expected_revision=rev)
    assert snapshot(c) == before


def test_E08_32_ordered_instances_and_33rd_refuses(tmp_path, backend):
    c = case(tmp_path, url=backend)
    for ordinal in range(32):
        instance(c, ordinal, 32)
        bind(c)
        retire_instance(c)
    assert len(journal(c)["instances"]) == 32 and len(canonical(journal(c))) <= 65536
    before = snapshot(c)
    with pytest.raises(REJECT):
        instance(c, 32, 32)
    assert snapshot(c) == before


@pytest.mark.parametrize("length", [65536, 65537])
def test_E08_exact_journal_byte_cap_admission(tmp_path, backend, length):
    c = case(tmp_path, url=backend)
    launch = {**c.launch, "image": "x@" + c.launch["image"]}
    identity = digest({"sandbox_id": c.reservation["sandbox_id"], "ordinal": 0, "source": c.source,
        "backend": c.backend.backend, "launch": launch})
    expected = {"schema": 1, "profile": "docker_environment_journal_v1", "revision": 1, "phase": "open",
        "backend": c.backend.backend, "source": c.source, "max_instances": 1, "instances": [{
            "ordinal": 0, "intent_id": identity, "name": "cam-sandbox-" + identity[:48], "creation_nonce": "0" * 32,
            "launch": launch, "state": "create_intent", "container_id": None,
            "create_observation_ref": None, "retirement_observation_ref": None}]}
    launch["image"] = "x" * (1 + length - len(canonical(expected))) + "@" + c.launch["image"]
    before = snapshot(c)
    if length == 65536:
        instance(c, **launch)
        assert len(canonical(journal(c))) == 65536
    else:
        with pytest.raises(REJECT, match="byte bound"):
            instance(c, **launch)
        assert snapshot(c) == before
    assert not c.fake.effects


@pytest.mark.parametrize("length", [16384, 16385])
def test_E08_observation_reference_cap_precedes_materialization(tmp_path, backend, monkeypatch, length):
    c = case(tmp_path, url=backend)
    instance(c)
    row = journal(c)["instances"][0]
    raw = canonical({"padding": "x" * (length - len(canonical({"padding": ""})))})
    assert len(raw) == length
    ref = c.artifacts.put(c.task["tenant_id"], c.task["task_id"], raw, "application/json")
    reads = []
    original = c.artifacts.get
    def observed(*a, **k):
        reads.append(k.get("max_bytes"))
        assert k.get("max_bytes") == 16384
        return original(*a, **k)
    monkeypatch.setattr(c.artifacts, "get", observed)
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.store.bind_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"], row["intent_id"],
            ref, expected_revision=journal(c)["revision"])
    assert reads == ([16384] if length == 16384 else [])
    assert snapshot(c) == before


def test_E06_retirement_write_loss_fences_next_case_until_absence_ack(tmp_path, backend, monkeypatch):
    c = case(tmp_path, url=backend)
    sandbox = started(c, max_instances=2)
    original = c.store.record_environment_retirement
    def failed(*a, **k):
        raise RuntimeError("independent retirement commit failed")
    monkeypatch.setattr(c.store, "record_environment_retirement", failed)
    with pytest.raises(REJECT):
        sandbox.close()
    assert not c.fake.containers and journal(c)["instances"][0]["state"] == "bound"
    before = snapshot(c)
    with pytest.raises(REJECT):
        instance(c, 1, 2)
    assert snapshot(c) == before
    monkeypatch.setattr(c.store, "record_environment_retirement", original)
    assert sandbox.close()["retired"] is True
    assert journal(c)["phase"] == "open"
    instance(c, 1, 2)
    assert len(journal(c)["instances"]) == 2


def test_E11_two_cleanup_controllers_reuse_stable_original_evidence(tmp_path, backend):
    from service.environment_recovery import DockerEnvironmentBackend, EnvironmentLifecycle, reconcile_environment
    c = case(tmp_path, url=backend)
    sandbox = started(c)
    peer_backend = DockerEnvironmentBackend("independent-local-docker", runner=c.fake)
    peer = EnvironmentLifecycle(c.store, c.artifacts, c.task["tenant_id"], c.task["task_id"],
        c.reservation["sandbox_id"], peer_backend)
    assert reconcile_environment(peer, peer_backend)["status"] == "retired"
    saved, before, effects = deepcopy(journal(c)), snapshot(c), deepcopy(c.fake.effects)
    assert sandbox.close()["retired"] is True
    assert reconcile(c)["status"] == "retired"
    assert journal(c) == saved and snapshot(c) == before and c.fake.effects == effects


@pytest.mark.parametrize("identity", ["source", "backend", "max_instances"])
def test_E01_changed_journal_identity_cannot_reinitialize_same_reservation(tmp_path, backend, identity):
    c = case(tmp_path, url=backend)
    instance(c)
    request = {"source": deepcopy(c.source), "backend": deepcopy(c.backend.backend),
        "max_instances": 1, "ordinal": 0, "launch": c.launch}
    if identity == "source":
        request["source"]["input_digest"] = "f" * 64
    elif identity == "backend":
        request["backend"]["daemon_id"] = "a-valid-different-daemon"
    else:
        request["max_instances"] = 2
    before = snapshot(c)
    with pytest.raises(REJECT):
        c.store.begin_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"], **request)
    assert snapshot(c) == before and not c.fake.effects


@pytest.mark.parametrize("proof", ["create_observation_ref", "retirement_observation_ref"])
def test_E07_forged_terminal_original_receipt_cannot_release_slot(tmp_path, backend, proof):
    c = case(tmp_path, url=backend)
    sandbox = started(c)
    sandbox.close()
    c.store.request_environment_cleanup(c.task["tenant_id"], c.reservation["sandbox_id"])
    j = journal(c)
    original_ref = j["instances"][0][proof]
    value = c.artifacts.get_json(c.task["tenant_id"], c.task["task_id"], original_ref["digest"])
    value["creation_nonce"] = "f" * 32
    value["operation_id"] = digest({k: v for k, v in value.items() if k != "operation_id"})
    forged = c.artifacts.put_json(c.task["tenant_id"], c.task["task_id"], value)
    with c.store._tx() as (connection, guard):
        row = c.store._get(connection, "sandboxes", c.reservation["sandbox_id"], c.task["tenant_id"])
        row["environment_journal"]["instances"][0][proof] = forged
        c.store._save(connection, "sandboxes", row["sandbox_id"], c.task["tenant_id"], c.task["task_id"], row)
    before, effects = snapshot(c), deepcopy(c.fake.effects)
    with pytest.raises(REJECT):
        c.lifecycle.close()
    assert snapshot(c) == before and c.fake.effects == effects
    assert snapshot(c)["sandboxes"][0]["status"] == "reserved"


def test_E05_cleanup_rechecks_incarnation_after_physical_inspection(tmp_path, backend, monkeypatch):
    c = case(tmp_path, url=backend)
    sandbox = started(c)
    original = c.backend.inspect_owned
    def revoke_after_inspection(row):
        result = original(row)
        c.store.quarantine_restore("independent physical-preflight incarnation replacement")
        return result
    monkeypatch.setattr(c.backend, "inspect_owned", revoke_after_inspection)
    before_effects = deepcopy(c.fake.effects)
    with pytest.raises(REJECT):
        sandbox.close()
    assert c.fake.effects == before_effects, "Stale cleanup must not remove after incarnation changes in inspection"
    assert CID in c.fake.containers
    assert journal(c)["instances"][0]["state"] == "bound"


def test_E06_concurrent_admission_has_one_create_winner_and_one_nonce(tmp_path, backend):
    from service.environment_recovery import EnvironmentBinding
    from service.execution import DockerSandbox
    from test_environment_recovery import FILES, IMAGE, observation
    c = case(tmp_path, url=backend)
    gate = threading.Barrier(2)
    def admit():
        gate.wait(timeout=10)
        return c.store.begin_environment_instance(c.task["tenant_id"], c.reservation["sandbox_id"], source=c.source,
            backend=c.backend.backend, max_instances=1, ordinal=0, launch=c.launch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: admit(), range(2)))
    winner = first if not first["duplicate"] else second
    duplicate = second if second["duplicate"] else first
    assert winner["duplicate"] is False and duplicate["duplicate"] is True
    assert winner["instance"] == duplicate["instance"]
    before = snapshot(c)
    with pytest.raises(REJECT):
        DockerSandbox(IMAGE, journal_binding=EnvironmentBinding(c.lifecycle, duplicate)).start(FILES)
    assert snapshot(c) == before and not c.fake.effects
    def created(argv):
        row = journal(c)["instances"][0]
        assert row == winner["instance"] and row["state"] == "create_intent"
        assert "coding-agent-mastery-create-nonce=" + row["creation_nonce"] in argv
        c.fake.install(row)
    c.fake.on_create, c.fake.create_fault = created, observation((CID + "\n").encode())
    sandbox = DockerSandbox(IMAGE, journal_binding=EnvironmentBinding(c.lifecycle, winner))
    sandbox.start(FILES)
    assert len([argv for argv in c.fake.effects if argv[1] == "create"]) == 1
    sandbox.close()
    assert reconcile(c)["status"] == "retired"


@pytest.mark.parametrize("stage", ["intent", "bind", "retire"])
def test_E04_transaction_event_fault_retains_conservative_original_state(tmp_path, monkeypatch, backend, stage):
    c = case(tmp_path, url=backend)
    if stage != "intent":
        instance(c)
    if stage == "retire":
        bind(c)
    before = snapshot(c)
    original = c.store._event
    def fault(*a, **k):
        if any(isinstance(x, str) and x.startswith("environment.") for x in a):
            raise RuntimeError("independent environment event failure")
        return original(*a, **k)
    monkeypatch.setattr(c.store, "_event", fault)
    with pytest.raises(RuntimeError, match="event failure"):
        if stage == "intent":
            instance(c)
        elif stage == "bind":
            bind(c)
        else:
            retire_instance(c)
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["cancel", "deadline", "quarantine", "incarnation"])
def test_E05_no_new_execution_but_fresh_cleanup_can_retire(tmp_path, backend, fault):
    from service.environment_recovery import DockerEnvironmentBackend, EnvironmentLifecycle
    c = case(tmp_path, url=backend)
    sandbox = started(c)
    if fault == "cancel":
        c.store.cancel(c.task["tenant_id"], c.task["task_id"], "cancel-environment")
    elif fault == "deadline":
        with c.store._tx() as (connection, guard):
            task = c.store._task(connection, c.task["tenant_id"], c.task["task_id"])
            task["contract"]["execution_deadline"] = 0
            c.store._save(connection, "tasks", c.task["task_id"], c.task["tenant_id"], c.task["task_id"], task)
    else:
        c.store.quarantine_restore("fresh-environment-controller", {"backup": "independent-test"})
    before = len(c.fake.effects)
    with pytest.raises(REJECT):
        sandbox.run(["python", "-c", "must not execute"])
    assert len(c.fake.effects) == before
    if fault in {"quarantine", "incarnation"}:
        with pytest.raises(REJECT):
            c.store.request_environment_cleanup(c.task["tenant_id"], c.reservation["sandbox_id"])
        fresh = RuntimeStore(c.store.engine.url.render_as_string(hide_password=False), c.artifacts)
        backend_object = DockerEnvironmentBackend("independent-local-docker", runner=c.fake)
        c.lifecycle = EnvironmentLifecycle(fresh, c.artifacts, c.task["tenant_id"], c.task["task_id"], c.reservation["sandbox_id"], backend_object)
        c.store, c.backend = fresh, backend_object
    assert reconcile(c)["status"] == "retired"
    assert snapshot(c)["sandboxes"][0]["status"] == "retired"
    assert snapshot(c)["task"]["execution_state"] != "review_eligible"


def test_E10_physical_cleanup_never_settles_unknown_model_or_creates_pass(tmp_path, backend):
    c = case(tmp_path, url=backend)
    c.store.set_graph(c.task["tenant_id"], c.task["task_id"], 1, [{"node_id": "worker"}])
    owner = c.store.claim(c.task["tenant_id"], c.task["task_id"], "worker", "claim-worker", 40, 300)["owner"]
    c.store.begin_dispatch(owner, "unknown-model", "unknown-model", "model.scripted", digest({"request": "unknown"}), 12)
    c.store.finish_dispatch(c.task["tenant_id"], "unknown-model", "lost-response", "unknown")
    instance(c)
    c.fake.install(journal(c)["instances"][0])
    before = snapshot(c)
    assert reconcile(c)["status"] == "retired"
    after = snapshot(c)
    assert after["dispatches"] == before["dispatches"] and after["budget"] == before["budget"]
    assert after["verifications"] == before["verifications"] == []
    assert after["task"]["execution_state"] == before["task"]["execution_state"]


def test_E11_cleanup_slot_release_ack_loss_converges_once(tmp_path, monkeypatch, backend):
    c = case(tmp_path, url=backend)
    sandbox = started(c)
    sandbox.close()
    original = c.store.retire_sandbox
    def lost_ack(*a, **k):
        original(*a, **k)
        raise RuntimeError("slot retirement ACK lost")
    monkeypatch.setattr(c.store, "retire_sandbox", lost_ack)
    with pytest.raises(RuntimeError, match="ACK lost"):
        reconcile(c)
    before = snapshot(c)
    monkeypatch.setattr(c.store, "retire_sandbox", original)
    effects = deepcopy(c.fake.effects)
    assert reconcile(c)["status"] == "retired" and snapshot(c) == before and c.fake.effects == effects
