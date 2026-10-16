"""2026-10-10 frozen authority boundary regressions; disposable local evidence."""

import asyncio
import math

import httpx
import pytest
import sqlalchemy as sa

from service.api import Principal, create_app
from service.artifacts import LocalArtifacts, digest_json
from service.contracts import timestamp
from service.engine import ReferenceEngine
from service.execution import tree_digest
from service.recovery import recovery_plan
from service.storage import RuntimeStore, TABLES, event_rows
from service.verification import FixtureVerifier, LinuxVerifier
from workloads import list_tasks
from workloads.registry import ROOT, TARGET_FILES


@pytest.fixture
def runtime(tmp_path):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(tmp_path / "state.sqlite"), artifacts)
    engine = ReferenceEngine(store, artifacts, tmp_path / "workers")
    yield store, artifacts, engine
    store.close()


def fixture_task(engine):
    return engine.submit_fixture(list_tasks(tier="T3")[0].task_id)


@pytest.mark.parametrize("field", ["requirements", "requirements_order", "grader_digest",
                                   "base_revision", "environment_digest", "model", "repo_id", "unknown_fixture"])
def test_fixture_preflight_rejects_contract_drift_before_effects(runtime, monkeypatch, field):
    store, _, engine = runtime
    source = fixture_task(engine)
    contract = dict(source["contract"])
    if field == "requirements":
        contract[field] = ["Also solve an entirely different requirement"]
    elif field == "requirements_order":
        assert len(contract["requirements"]) > 1
        contract["requirements"] = list(reversed(contract["requirements"]))
    elif field == "model":
        contract[field] = "different-model"
    elif field == "repo_id":
        contract[field] = "unsupported-repository"
    elif field == "unknown_fixture":
        contract["repo_id"] = "synthetic-issue-tracker:missing-fixture"
    else:
        contract[field] = digest_json("wrong-" + field)
    task = store.submit("demo", "drift", contract)
    before = store.snapshot("demo", task["task_id"])
    invocations = []
    monkeypatch.setattr(engine.verifier, "verify", lambda *a, **k: invocations.append((a, k)))
    with pytest.raises(ValueError):
        engine.run_task("demo", task["task_id"])
    assert invocations == []
    assert store.snapshot("demo", task["task_id"]) == before
    assert all(before[name] == [] for name in
               ("nodes", "attempts", "dispatches", "candidates", "sandboxes", "verifications"))


@pytest.mark.parametrize("field", ["tree_digest", "grader_digest", "environment_digest", "passed"])
@pytest.mark.parametrize("mutation", ["wrong", "missing"])
@pytest.mark.parametrize("passed", [True, False])
def test_untrusted_verifier_metadata_cannot_author_receipt(runtime, monkeypatch, field, mutation, passed):
    store, artifacts, engine = runtime
    task = fixture_task(engine)
    returned = {}

    def forged(files, selected, **_):
        result = {"passed": passed, "tree_digest": tree_digest(files),
                  "grader_digest": selected.as_dict()["grader_sha256"],
                  "environment_digest": engine.verifier.environment_digest}
        if mutation == "missing":
            result.pop(field)
        else:
            result[field] = "true" if field == "passed" else digest_json("wrong-" + field)
        returned.update(result)
        return result

    monkeypatch.setattr(engine.verifier, "verify", forged)
    with pytest.raises(ValueError, match="verifier"):
        engine.run_task("demo", task["task_id"])
    snapshot = store.snapshot("demo", task["task_id"])
    assert snapshot["verifications"] == [] and snapshot["reviews"] == []
    assert snapshot["task"]["execution_state"] != "review_eligible"
    assert all(s["status"] == "retired" for s in snapshot["sandboxes"])
    assert artifacts.get_json("demo", task["task_id"], digest_json(returned)) == returned


@pytest.mark.parametrize("verdict", [0, 1, None, [], {}])
def test_verifier_verdict_requires_boolean(runtime, monkeypatch, verdict):
    store, _, engine = runtime
    task = fixture_task(engine)
    original = engine.verifier.verify

    def altered(*args, **kwargs):
        return {**original(*args, **kwargs), "passed": verdict}

    monkeypatch.setattr(engine.verifier, "verify", altered)
    with pytest.raises(ValueError, match="verifier"):
        engine.run_task("demo", task["task_id"])
    assert store.snapshot("demo", task["task_id"])["verifications"] == []


def test_linux_returned_identity_rejection_keeps_confirmed_retirement(runtime, monkeypatch):
    store, artifacts, engine = runtime
    task = fixture_task(engine)
    verifier = object.__new__(LinuxVerifier)  # Mock trusted boundary; no Docker invocation.
    verifier.environment_digest = engine.verifier.environment_digest
    engine.verifier = verifier
    returned = {}

    def forged(files, selected, sandbox_id):
        result = {"passed": True, "tree_digest": tree_digest(files),
                  "grader_digest": digest_json("wrong-grader"),
                  "environment_digest": verifier.environment_digest,
                  "retirement": {"sandbox_id": sandbox_id, "retired": True}}
        returned.update(result)
        return result

    monkeypatch.setattr(verifier, "verify", forged)
    with pytest.raises(ValueError, match="verifier"):
        engine.run_task("demo", task["task_id"])
    snapshot = store.snapshot("demo", task["task_id"])
    assert all(s["status"] == "retired" for s in snapshot["sandboxes"])
    assert snapshot["verifications"] == []
    assert artifacts.get_json("demo", task["task_id"], digest_json(returned)) == returned


def test_valid_failed_verifier_receipt_keeps_exact_identities(runtime, monkeypatch):
    store, _, engine = runtime
    task = fixture_task(engine)
    original = engine.verifier.verify

    def failed(*args, **kwargs):
        return {**original(*args, **kwargs), "passed": False, "cause": "controlled-failure"}

    monkeypatch.setattr(engine.verifier, "verify", failed)
    result = engine.run_task("demo", task["task_id"])
    assert result["task"]["execution_state"] == "failed"
    assert len(result["verifications"]) == 1 and result["reviews"] == []
    receipt = result["verifications"][0]
    assert receipt["outcome"] == "fail"
    for field in ("tree_digest", "grader_digest", "environment_digest"):
        assert receipt[field] == result["verification_detail"][field]


def test_linux_image_preflight_rejects_exit_zero_with_uncertain_completion(monkeypatch):
    import service.verification as verification

    monkeypatch.setattr(verification, "bounded_process", lambda *args, **kwargs: {
        "exit_code": 0, "output": b"sha256:test amd64 linux\n", "reason": "timeout",
        "process_group_retired": True, "truncated": False,
    })
    with pytest.raises(ValueError, match="immutable image"):
        LinuxVerifier("test-only-image")


def test_linux_image_preflight_keeps_acknowledged_result_valid(monkeypatch):
    import service.verification as verification

    monkeypatch.setattr(verification, "bounded_process", lambda *args, **kwargs: {
        "exit_code": 0, "output": b"sha256:test amd64 linux\n", "reason": "exited",
        "process_group_retired": True, "truncated": False,
    })
    assert len(LinuxVerifier("test-only-image").environment_digest) == 64


def test_terminal_replay_remains_historical_read_after_registry_and_environment_drift(runtime, monkeypatch):
    import workloads.registry as registry

    store, _, engine = runtime
    task = fixture_task(engine)
    engine.run_task("demo", task["task_id"])
    before = store.snapshot("demo", task["task_id"])
    engine.verifier.environment_digest = digest_json("new-environment")

    def drift():
        raise ValueError("new registry drift")

    monkeypatch.setattr(registry, "validate_assets", drift)
    assert engine.run_task("demo", task["task_id"]) == before


@pytest.mark.parametrize("source", ["reference", "baseline", "unknown"])
def test_cpu_verifier_returns_complete_identities_for_pass_fail_and_unsupported(source):
    task = list_tasks(tier="T3")[0]
    directory = ROOT / "oracle/reference" if source == "reference" else task.baseline_path
    files = {p: (directory / p).read_text() for p in TARGET_FILES}
    if source == "unknown":
        files["issue_tracker.py"] = "raise AssertionError('must not execute')\n"
    verifier = FixtureVerifier()
    result = verifier.verify(files, task)
    assert result["passed"] is (source == "reference")
    assert result["tree_digest"] == tree_digest(files)
    assert result["grader_digest"] == task.as_dict()["grader_sha256"]
    assert result["environment_digest"] == verifier.environment_digest


@pytest.mark.parametrize("value", [10**400, -(10**400), True, False, float("inf"), float("nan")])
def test_timestamp_rejects_unrepresentable_or_invalid_numeric_values_as_valueerror(value):
    with pytest.raises(ValueError):
        timestamp(value, "deadline")


@pytest.mark.parametrize("value", [0, 0.25, 2**53, 1e308, "1970-01-01T00:00:00Z"])
def test_timestamp_preserves_valid_finite_domain(value):
    expected = 0.0 if isinstance(value, str) else float(value)
    assert timestamp(value, "deadline") == expected and math.isfinite(expected)


@pytest.mark.parametrize("error", [OverflowError, OSError])
def test_timestamp_classifies_platform_date_conversion_failure(monkeypatch, error):
    import service.contracts as contracts

    class PlatformDate:
        tzinfo = object()

        @staticmethod
        def fromisoformat(_):
            return PlatformDate()

        def timestamp(self):
            raise error("platform timestamp out of range")

    monkeypatch.setattr(contracts, "datetime", PlatformDate)
    with pytest.raises(ValueError, match="deadline"):
        timestamp("9999-12-31T23:59:59+00:00", "deadline")


@pytest.mark.parametrize("field", ["execution_deadline", "review_deadline"])
def test_oversized_deadline_http_rejection_has_no_durable_effects(runtime, field):
    store, _, _ = runtime
    token = "disposable-authority-regression-token"
    app = create_app(store, tokens={token: Principal("tenant", "user", frozenset({"fixture"}))})

    def counts():
        with store.engine.connect() as connection:
            return {name: connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
                    for name, table in {**TABLES, "task_events": event_rows}.items()}

    before = counts()

    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://reference.test") as client:
            return await client.post("/tasks", headers={"Authorization": "Bearer " + token},
                                     json={"key": "oversized", "contract": {
                                         "repo_id": "fixture", "base_revision": "base",
                                         "requirements": ["repair"], field: 10**400}})

    response = asyncio.run(call())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert counts() == before and store.list_outbox() == []


@pytest.mark.parametrize("obligations", ["none", "retained", "unknown", "quarantined"])
def test_failed_task_recovery_preserves_obligation_precedence(runtime, obligations):
    store, artifacts, engine = runtime
    task = fixture_task(engine)
    if obligations != "none":
        store.set_graph("demo", task["task_id"], task["generation"], [{"node_id": "patch"}])
        owner = store.claim("demo", task["task_id"], "patch", "claim", 10, 60)["owner"]
        if obligations in {"unknown", "quarantined"}:
            store.begin_dispatch(owner, "action", "dispatch", "read", digest_json({}), 1)
    evidence = artifacts.put_json("demo", task["task_id"], {"observed": "fixture failure"})
    store.fail_execution("demo", task["task_id"], task["generation"], "infrastructure_failed", evidence)
    if obligations == "quarantined":
        store.quarantine_restore("fresh-incarnation", {"source": "disposable regression"})
    snapshot = store.snapshot("demo", task["task_id"])
    assert snapshot["task"]["execution_state"] == "failed"
    plan = recovery_plan(snapshot)
    assert plan["next_step"] == {
        "none": "settlement_or_review_only", "retained": "confirm_environment_retirement",
        "unknown": "reconcile_effects_before_replacement", "quarantined": "operator_restore_reconciliation",
    }[obligations]
    assert plan["unknown_dispatches"] == (["dispatch"] if obligations in {"unknown", "quarantined"} else [])
    assert plan["retained_sandboxes"] == [s["sandbox_id"] for s in snapshot["sandboxes"]
                                          if s["status"] != "retired"]
