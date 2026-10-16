import asyncio
import os
from types import SimpleNamespace

import pytest

from service.storage import RuntimeStore
from service.workflows import (
    CodingTaskWorkflow,
    LocalOutboxDispatcher,
    TaskActivities,
    TemporalOutboxRelay,
    WorkflowAlreadyStartedError,
    workflow_id,
    workflow_request,
)


@pytest.fixture
def store(tmp_path):
    value = RuntimeStore(f"sqlite:///{tmp_path / 'runtime.sqlite'}")
    value.submit(
        "tenant", "submission", {"repo_id": "repo", "base_revision": "base", "requirements": ["repair"]}
    )
    yield value
    value.close()


class FakeTemporalClient:
    """Transport mock only; not evidence of a Temporal server."""

    def __init__(self, *, ambiguous_first=False):
        self.started = {}
        self.ambiguous_first = ambiguous_first

    async def start_workflow(self, _workflow, request, **kwargs):
        identifier = kwargs["id"]
        if identifier in self.started:
            raise WorkflowAlreadyStartedError(identifier, "CodingTaskWorkflowV1", run_id="fake-run")
        self.started[identifier] = {"request": request, **kwargs}
        if self.ambiguous_first:
            self.ambiguous_first = False
            raise TimeoutError("transport acknowledgement lost after server start")
        return SimpleNamespace(id=identifier)

    def get_workflow_handle(self, identifier):
        async def memo():
            return self.started[identifier]["memo"]

        async def describe():
            return SimpleNamespace(memo=memo)

        return SimpleNamespace(describe=describe)


def test_local_outbox_duplicate_safe_and_failed_dispatch_retained(store):
    observations = []

    def fail(_tenant, _task):
        raise RuntimeError("injected unavailable runner")

    assert LocalOutboxDispatcher(store, fail).dispatch_once()[0]["status"] == "pending_retry"
    assert len(store.list_outbox()) == 1
    dispatcher = LocalOutboxDispatcher(store, lambda tenant, task: observations.append((tenant, task)) or {})
    assert dispatcher.dispatch_once()[0]["status"] == "dispatched"
    assert dispatcher.dispatch_once() == []
    assert len(observations) == 1


def test_local_cancelled_start_is_suppressed(store):
    command = store.list_outbox()[0]
    store.cancel("tenant", command["task_id"], "cancel")
    invoked = []
    result = LocalOutboxDispatcher(store, lambda *args: invoked.append(args)).dispatch_once()
    assert result[0]["status"] == "suppressed_stale_or_terminal"
    assert invoked == []


def test_temporal_ambiguous_start_reconciles_stable_identity_then_acks(store):
    client = FakeTemporalClient(ambiguous_first=True)
    relay = TemporalOutboxRelay(store, client, task_queue="reference")
    first = asyncio.run(relay.dispatch_once())
    assert first[0]["status"] == "pending_retry"
    assert len(store.list_outbox()) == 1
    second = asyncio.run(relay.dispatch_once())
    assert second[0]["status"] == "existing_start_reconciled"
    assert store.list_outbox() == []
    assert len(client.started) == 1


def test_temporal_identity_mismatch_does_not_ack(store):
    client = FakeTemporalClient(ambiguous_first=True)
    relay = TemporalOutboxRelay(store, client, task_queue="reference")
    asyncio.run(relay.dispatch_once())
    next(iter(client.started.values()))["memo"]["command_id"] = "wrong-command"
    assert asyncio.run(relay.dispatch_once())[0]["status"] == "pending_retry"
    assert len(store.list_outbox()) == 1


def test_restore_suppresses_pre_restore_start_and_activity(store):
    command = store.list_outbox()[0]
    request = workflow_request(command)
    store.quarantine_restore("new-incarnation", {"backup": 1})
    client = FakeTemporalClient()
    result = asyncio.run(TemporalOutboxRelay(store, client, task_queue="reference").dispatch_once())
    assert result[0]["status"] == "suppressed_stale_or_terminal"
    assert client.started == {}
    invoked = []
    activities = TaskActivities(store, lambda request: invoked.append(request) or {"done": True})
    outcome = asyncio.run(activities.run_step(request))
    assert outcome["outcome"]["status"] == "authority_revoked"
    assert invoked == []


def test_activity_provides_stable_step_key_and_requires_explicit_outcome(store):
    command = store.list_outbox()[0]
    request = workflow_request(command)
    keys = []
    activity = TaskActivities(
        store, lambda payload: keys.append(payload["idempotency_key"]) or {"done": False}
    )
    assert asyncio.run(activity.run_step(request))["done"] is False
    assert asyncio.run(activity.run_step(request))["done"] is False
    assert keys == [f"{workflow_id(command)}:step:0"] * 2
    # This wrapper deliberately does not cache: injected step must use receipts.
    bad = TaskActivities(store, lambda _payload: {"passed": True})
    with pytest.raises(ValueError):
        asyncio.run(bad.run_step(request))


def test_temporal_workflow_rejects_zero_or_boolean_limits(store):
    command = store.list_outbox()[0]
    for value in (0, -1, True, 129):
        with pytest.raises(ValueError):
            workflow_request(command, max_steps=value)


def test_temporary_execution_pause_keeps_current_start_pending(store, monkeypatch):
    original = store.service_state
    monkeypatch.setattr(store, "service_state", lambda: dict(original(), execution_enabled=False))
    invoked = []
    local = LocalOutboxDispatcher(store, lambda *args: invoked.append(args))
    assert local.dispatch_once()[0]["status"] == "pending_retry"
    assert len(store.list_outbox()) == 1
    client = FakeTemporalClient()
    relay = TemporalOutboxRelay(store, client, task_queue="reference")
    assert asyncio.run(relay.dispatch_once())[0]["status"] == "pending_retry"
    assert client.started == {}
    assert invoked == []


@pytest.mark.parametrize("transport", ["local", "temporal"])
def test_over_100_domain_notifications_cannot_permanently_starve_new_start(store, transport):
    first = store.list_outbox()[0]
    store.ack_outbox(first["command_id"])
    task_id = first["task_id"]
    store.set_graph("tenant", task_id, 1, [{"id": "worker"}])
    owner = store.claim("tenant", task_id, "worker", "claim", 0, 600)["owner"]
    for index in range(101):
        store.begin_dispatch(owner, f"action-{index}", f"dispatch-{index}", "test", "a" * 64, 0)
    second = store.submit(
        "tenant",
        "new-submission",
        {"repo_id": "repo", "base_revision": "base", "requirements": ["next repair"]},
    )
    assert len(store.list_outbox(limit=1000)) == 102
    invoked = []
    if transport == "local":
        dispatcher = LocalOutboxDispatcher(store, lambda tenant, task: invoked.append((tenant, task)) or {})
        results = dispatcher.dispatch_once(limit=100) + dispatcher.dispatch_once(limit=100)
        assert invoked == [("tenant", second["task_id"])]
    else:
        client = FakeTemporalClient()
        relay = TemporalOutboxRelay(store, client, task_queue="reference")
        results = asyncio.run(relay.dispatch_once(limit=100)) + asyncio.run(relay.dispatch_once(limit=100))
        assert len(client.started) == 1
        assert next(iter(client.started.values()))["request"]["task_id"] == second["task_id"]
    assert sum(result["status"] == "domain_notification_observed" for result in results) == 101
    assert store.list_outbox(limit=1000) == []
    # Observing intent notifications does not execute or settle those effects.
    assert all(row["effect_state"] == "in_flight" for row in store.snapshot("tenant", task_id)["dispatches"])


def test_unknown_outbox_kind_remains_pending_without_blocking_start(store):
    command = store.list_outbox()[0]
    store.ack_outbox(command["command_id"])
    # Seed an unsupported transport command in a disposable store fixture.
    with store._tx() as (connection, guard):
        task = store._task(connection, "tenant", command["task_id"])
        for index in range(101):
            store._command(connection, guard, task, "unsupported_notification", {"index": index})
    second = store.submit(
        "tenant", "second", {"repo_id": "repo", "base_revision": "base", "requirements": ["next repair"]}
    )
    invoked = []
    result = LocalOutboxDispatcher(store, lambda tenant, task: invoked.append(task) or {}).dispatch_once()
    assert result[0]["status"] == "dispatched"
    assert invoked == [second["task_id"]]
    assert len(store.list_outbox(limit=1000)) == 101


@pytest.mark.temporal
@pytest.mark.skipif(
    os.environ.get("CAM_TEST_TEMPORAL") != "1", reason="requires explicit local Temporal dev-server opt-in"
)
def test_real_local_temporal_workflow_continue_as_new_and_history_replay(store, tmp_path):
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Replayer, Worker

    async def exercise():
        command = store.list_outbox()[0]
        recorded = []

        def step(payload):
            recorded.append(payload["idempotency_key"])
            return {"done": payload["step_index"] == 2, "outcome": {"status": "trusted-fixture-step"}}

        activities = TaskActivities(store, step)
        # Explicit local-only SDK server; no hosted service, model or paid call.
        environment = await WorkflowEnvironment.start_local(ip="127.0.0.1", ui=False)
        async with environment:
            async with Worker(
                environment.client,
                task_queue="reference-local-test",
                workflows=[CodingTaskWorkflow],
                activities=[activities.run_step],
            ):
                handle = await environment.client.start_workflow(
                    CodingTaskWorkflow.run,
                    workflow_request(command, max_steps=4, history_batch=2),
                    id=workflow_id(command),
                    task_queue="reference-local-test",
                )
                result = await asyncio.wait_for(handle.result(), timeout=60)
                assert result["done"] is True
                assert len(recorded) == 3
                initial = environment.client.get_workflow_handle(
                    handle.id, run_id=handle.first_execution_run_id
                )
                history = await initial.fetch_history()
                (tmp_path / "initial-history.json").write_text(history.to_json())
                await Replayer(workflows=[CodingTaskWorkflow]).replay_workflow(history)
                continued = [
                    event.workflow_execution_continued_as_new_event_attributes.new_execution_run_id
                    for event in history.events
                    if event.HasField("workflow_execution_continued_as_new_event_attributes")
                ]
                assert len(continued) == 1
                final = environment.client.get_workflow_handle(handle.id, run_id=continued[0])
                final_history = await final.fetch_history()
                (tmp_path / "continued-history.json").write_text(final_history.to_json())
                await Replayer(workflows=[CodingTaskWorkflow]).replay_workflow(final_history)
                # Replayer consumes recorded activity results; it makes no new effects.
                assert len(recorded) == 3

    asyncio.run(exercise())


@pytest.mark.temporal
@pytest.mark.skipif(
    os.environ.get("CAM_TEST_TEMPORAL") != "1", reason="requires explicit local Temporal dev-server opt-in"
)
def test_real_temporal_duplicate_start_memo_and_stop_before_rollover(store, tmp_path, monkeypatch):
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Replayer, Worker

    async def exercise():
        command = store.list_outbox()[0]
        entered, release = asyncio.Event(), asyncio.Event()
        recorded = []

        async def step(payload):
            recorded.append(payload["idempotency_key"])
            entered.set()
            await release.wait()
            return {"done": False}

        activities = TaskActivities(store, step)
        original_ack = store.ack_outbox
        lose_ack = True

        def acknowledgement(command_id):
            nonlocal lose_ack
            if lose_ack:
                lose_ack = False
                raise TimeoutError("injected acknowledgement loss after real workflow start")
            original_ack(command_id)

        monkeypatch.setattr(store, "ack_outbox", acknowledgement)
        environment = await WorkflowEnvironment.start_local(ip="127.0.0.1", ui=False)
        async with environment:
            async with Worker(environment.client, task_queue="reference-stop-test",
                              workflows=[CodingTaskWorkflow], activities=[activities.run_step]):
                relay = TemporalOutboxRelay(store, environment.client, task_queue="reference-stop-test",
                                            max_steps=2, history_batch=1)
                assert (await relay.dispatch_once())[0]["status"] == "pending_retry"
                await asyncio.wait_for(entered.wait(), timeout=30)
                assert (await relay.dispatch_once())[0]["status"] == "existing_start_reconciled"
                handle = environment.client.get_workflow_handle(workflow_id(command))
                await handle.signal(CodingTaskWorkflow.stop)
                release.set()
                result = await asyncio.wait_for(handle.result(), timeout=30)
                assert result["outcome"]["status"] == "orchestration_stopped"
                assert len(recorded) == 1
                history = await handle.fetch_history()
                (tmp_path / "stop-before-rollover-history.json").write_text(history.to_json())
                assert not any(event.HasField("workflow_execution_continued_as_new_event_attributes")
                               for event in history.events)
                await Replayer(workflows=[CodingTaskWorkflow]).replay_workflow(history)
                assert len(recorded) == 1

    asyncio.run(exercise())
