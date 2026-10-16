"""At-least-once outbox bridges and a deterministic real Temporal workflow.

Injected task steps MUST enforce domain ownership/idempotence/effect receipts.
A successful transport start is not a candidate pass or effect receipt.
Optional Temporal dependency never silently becomes a local transport.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import timedelta
from typing import Any, Callable

from .contracts import Fenced, Unsupported, freeze, identity, strict_int

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
    from temporalio.exceptions import WorkflowAlreadyStartedError
except ImportError:
    activity = workflow = None
    RetryPolicy = WorkflowIDReusePolicy = WorkflowAlreadyStartedError = None


RUNNABLE_STATES = frozenset(("queued", "running"))
# These notify durable state already owned by the application task loop. They
# never authorize this bridge to execute a tool or create a verifier receipt.
DOMAIN_NOTIFICATIONS = frozenset(("dispatch", "candidate_ready", "verify", "review_ready"))


def workflow_id(command: dict) -> str:
    value = [command[key] for key in ("service_incarnation", "tenant_id", "task_id", "generation")]
    return "coding-task-" + hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def workflow_request(command: dict, *, max_steps=32, history_batch=16, activity_timeout_seconds=60) -> dict:
    for key in ("service_incarnation", "tenant_id", "task_id", "command_id"):
        identity(command[key], key)
    strict_int(command["generation"], "generation", 1)
    strict_int(max_steps, "max_steps", 1, 128)
    strict_int(history_batch, "history_batch", 1, 64)
    strict_int(activity_timeout_seconds, "activity_timeout_seconds", 1, 3600)
    return {
        key: command[key]
        for key in ("service_incarnation", "tenant_id", "task_id", "generation", "command_id")
    } | {
        "step_index": 0,
        "max_steps": max_steps,
        "history_batch": history_batch,
        "activity_timeout_seconds": activity_timeout_seconds,
    }


def _validate_request(request: dict):
    expected = {
        "service_incarnation",
        "tenant_id",
        "task_id",
        "generation",
        "command_id",
        "step_index",
        "max_steps",
        "history_batch",
        "activity_timeout_seconds",
    }
    if not isinstance(request, dict) or set(request) != expected:
        raise ValueError("invalid frozen workflow request")
    workflow_request(
        request,
        max_steps=request["max_steps"],
        history_batch=request["history_batch"],
        activity_timeout_seconds=request["activity_timeout_seconds"],
    )
    strict_int(request["step_index"], "step_index", 0, request["max_steps"])


if workflow is not None:

    @workflow.defn(name="CodingTaskWorkflowV1", failure_exception_types=[ValueError])
    class CodingTaskWorkflow:
        def __init__(self):
            self.stop_requested = False

        @workflow.signal
        def stop(self):
            self.stop_requested = True

        @workflow.run
        async def run(self, request: dict) -> dict:
            _validate_request(request)
            steps_this_history = 0
            for index in range(request["step_index"], request["max_steps"]):
                if self.stop_requested:
                    return {"done": True, "outcome": {"status": "orchestration_stopped"}}
                payload = dict(request, step_index=index)
                result = await workflow.execute_activity(
                    "coding_task_step_v1",
                    payload,
                    start_to_close_timeout=timedelta(seconds=request["activity_timeout_seconds"]),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                    activity_id=f"step-{index}",
                )
                # A signal can change this state while the activity is awaited.
                # Do not lose it by returning a result or starting a new history.
                if self.stop_requested:
                    return {"done": True, "outcome": {"status": "orchestration_stopped"}}
                if not isinstance(result, dict) or type(result.get("done")) is not bool:
                    raise ValueError("task activity must return explicit done boolean")
                if result["done"]:
                    return result
                steps_this_history += 1
                if steps_this_history >= request["history_batch"] and index + 1 < request["max_steps"]:
                    workflow.continue_as_new(dict(request, step_index=index + 1))
            if self.stop_requested:
                return {"done": True, "outcome": {"status": "orchestration_stopped"}}
            return {
                "done": False,
                "outcome": {
                    "status": "orchestration_step_budget_exhausted",
                    "limitation": "domain task outcome requires an authorized store transition",
                },
            }
else:

    class CodingTaskWorkflow:
        async def run(self, _request):
            raise Unsupported("Temporal SDK is not installed")


class TaskActivities:
    """Perform one injected idempotent application step, outside workflow replay.

    Preflight fences known stale requests. It is not an atomic lease: the step
    must recheck current authority at each effect/acceptance boundary itself.
    No transport-memory cache is used to substitute for durable effect receipts.
    """

    def __init__(self, store, step: Callable[[dict], Any]):
        self.store, self.step = store, step

    async def _step(self, request: dict) -> dict:
        _validate_request(request)
        authority = self.store.service_state()
        task = self.store.get_task(request["tenant_id"], request["task_id"])
        if (
            authority["service_incarnation"] != request["service_incarnation"]
            or not authority["execution_enabled"]
            or authority["quarantined"]
            or task["generation"] != request["generation"]
            or task["execution_state"] not in RUNNABLE_STATES
        ):
            return {
                "done": True,
                "outcome": {"status": "authority_revoked", "execution_state": task["execution_state"]},
            }
        payload = freeze(request)
        payload["idempotency_key"] = f"{workflow_id(request)}:step:{request['step_index']}"
        if inspect.iscoroutinefunction(self.step):
            result = await self.step(payload)
        else:
            # Temporal async activity must not block its event loop on local I/O.
            import asyncio

            result = await asyncio.to_thread(self.step, payload)
            if inspect.isawaitable(result):
                result = await result
        if not isinstance(result, dict) or type(result.get("done")) is not bool:
            raise ValueError("injected task step must return explicit done boolean")
        return freeze(result)

    if activity is not None:

        @activity.defn(name="coding_task_step_v1")
        async def run_step(self, request: dict) -> dict:
            return await self._step(request)
    else:

        async def run_step(self, request: dict) -> dict:
            raise Unsupported("Temporal SDK is not installed")


def _is_current_start(command, task, authority) -> bool:
    return (
        command["service_incarnation"] == authority["service_incarnation"]
        and command["generation"] == task["generation"]
        and task["execution_state"] in RUNNABLE_STATES
    )


def _admit_start(authority):
    # A temporary execution pause must retain durable queued intent, not ack it.
    if not authority["execution_enabled"] or authority["quarantined"]:
        raise Fenced("execution is paused; start remains pending")


class LocalOutboxDispatcher:
    """Trusted reference bridge. Failed steps retain outbox entries for retry.

    The injected synchronous runner is responsible for durable step/effect
    identities. Cancellation requires an explicit local cleanup callback.
    """

    def __init__(self, store, run_task: Callable[[str, str], dict], *, stop_task=None):
        self.store, self.run_task, self.stop_task = store, run_task, stop_task

    def dispatch_once(self, limit=100) -> list[dict]:
        strict_int(limit, "outbox limit", 1, 1000)
        results = []
        kinds = DOMAIN_NOTIFICATIONS | {"start"}
        if self.stop_task is not None:
            kinds |= {"stop_sandbox"}
        for command in self.store.list_outbox(limit=limit, kinds=kinds):
            try:
                task = self.store.get_task(command["tenant_id"], command["task_id"])
                authority = self.store.service_state()
                if command["kind"] in DOMAIN_NOTIFICATIONS:
                    outcome = "domain_notification_observed"
                elif command["kind"] == "start":
                    if not _is_current_start(command, task, authority):
                        outcome = "suppressed_stale_or_terminal"
                    else:
                        _admit_start(authority)
                        self.run_task(command["tenant_id"], command["task_id"])
                        outcome = "dispatched"
                elif command["kind"] == "stop_sandbox":
                    if self.stop_task is None:
                        raise Unsupported("local cancellation cleanup callback is not configured")
                    self.stop_task(command)
                    outcome = "stop_delivered"
                else:
                    raise Unsupported("unsupported local outbox command")
                self.store.ack_outbox(command["command_id"])
                results.append({"command_id": command["command_id"], "status": outcome})
            except Exception as error:
                results.append(
                    {
                        "command_id": command["command_id"],
                        "status": "pending_retry",
                        "error_type": type(error).__name__,
                    }
                )
        return results


class TemporalOutboxRelay:
    """Start/signal transport with stable identities; ack follows reconciliation."""

    def __init__(
        self, store, client, *, task_queue: str, max_steps=32, history_batch=16, activity_timeout_seconds=60
    ):
        if workflow is None:
            raise Unsupported("Temporal SDK is not installed")
        identity(task_queue, "task_queue")
        self.store, self.client, self.task_queue = store, client, task_queue
        self.settings = dict(
            max_steps=max_steps,
            history_batch=history_batch,
            activity_timeout_seconds=activity_timeout_seconds,
        )

    async def dispatch_once(self, limit=100) -> list[dict]:
        strict_int(limit, "outbox limit", 1, 1000)
        results = []
        for command in self.store.list_outbox(limit=limit, kinds=DOMAIN_NOTIFICATIONS | {"start"}):
            try:
                task = self.store.get_task(command["tenant_id"], command["task_id"])
                authority = self.store.service_state()
                if command["kind"] in DOMAIN_NOTIFICATIONS:
                    outcome = "domain_notification_observed"
                elif command["kind"] == "start":
                    if not _is_current_start(command, task, authority):
                        outcome = "suppressed_stale_or_terminal"
                    else:
                        _admit_start(authority)
                        request = workflow_request(command, **self.settings)
                        identifier = workflow_id(command)
                        try:
                            await self.client.start_workflow(
                                CodingTaskWorkflow.run,
                                request,
                                id=identifier,
                                task_queue=self.task_queue,
                                execution_timeout=timedelta(
                                    seconds=request["max_steps"] * request["activity_timeout_seconds"] * 3
                                    + 120
                                ),
                                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                                memo={"command_id": command["command_id"], "task_identity": identifier},
                            )
                            outcome = "started"
                        except WorkflowAlreadyStartedError:
                            handle = self.client.get_workflow_handle(identifier)
                            description = await handle.describe()
                            memo = await description.memo()
                            if (
                                memo.get("command_id") != command["command_id"]
                                or memo.get("task_identity") != identifier
                            ):
                                raise Fenced("existing workflow identity does not match outbox command")
                            outcome = "existing_start_reconciled"
                elif command["kind"] == "stop_sandbox":
                    # Workflow signalling is not proof of physical retirement.
                    raise Unsupported("stop_sandbox requires an independently configured cleanup dispatcher")
                else:
                    raise Unsupported("unsupported Temporal outbox command")
                self.store.ack_outbox(command["command_id"])
                results.append({"command_id": command["command_id"], "status": outcome})
            except Exception as error:
                # Ambiguous start remains pending; next retry reconciles stable ID.
                results.append(
                    {
                        "command_id": command["command_id"],
                        "status": "pending_retry",
                        "error_type": type(error).__name__,
                    }
                )
        return results
