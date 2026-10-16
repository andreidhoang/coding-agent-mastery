"""Audit regressions: local injected transports only, no cloud calls."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from service.harness import Harness
from service.protocol import ProtocolError
from service.providers import AnthropicMessages
from service.workflows import CodingTaskWorkflow, TemporalOutboxRelay, WorkflowAlreadyStartedError, workflow_request
from test_live_harness import envelope, setup


def test_temporal_duplicate_start_awaits_sdk_memo(tmp_path):
    store, _, _, _, _ = setup(tmp_path)
    class Client:
        async def start_workflow(self, *_args, **kwargs):
            raise WorkflowAlreadyStartedError(kwargs['id'], 'CodingTaskWorkflowV1', run_id='test')
        def get_workflow_handle(self, identifier):
            async def memo():
                return {'command_id': store.list_outbox()[0]['command_id'], 'task_identity': identifier}
            async def describe():
                return SimpleNamespace(memo=memo)
            return SimpleNamespace(describe=describe)
    result = asyncio.run(TemporalOutboxRelay(store, Client(), task_queue='test').dispatch_once())
    assert result[0]['status'] == 'existing_start_reconciled', result


def test_billed_truncated_response_retains_receipt(tmp_path):
    store, artifacts, task, owner, workspace = setup(tmp_path)
    raw = {'type': 'message', 'role': 'assistant', 'model': 'pinned-test-model',
           'content': [{'type': 'text', 'text': 'Partial'}],
           'stop_reason': 'max_tokens', 'usage': {'input_tokens': 12, 'output_tokens': 100}}
    adapter = AnthropicMessages('mock', 'pinned-test-model', enable_network=True,
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=raw))))
    with pytest.raises((ProtocolError, RuntimeError)):
        Harness(store, artifacts, provider_envelopes={adapter.model: envelope()}).run(
            owner, task['contract'], workspace, adapter)
    dispatch = store.snapshot('tenant', task['task_id'])['dispatches'][0]
    assert dispatch['billing_state'] == 'settled', dispatch
    assert dispatch['actual_units'] == 3
    assert artifacts.get_json('tenant', task['task_id'], dispatch['result_ref']['digest']) == raw


@pytest.mark.parametrize("max_steps,activity_done", [(2, False), (1, False), (2, True)])
def test_stop_during_last_activity_is_not_lost_on_continue_as_new(tmp_path, monkeypatch, max_steps, activity_done):
    import service.workflows as workflows
    store, _, _, _, _ = setup(tmp_path)
    instance = CodingTaskWorkflow()
    async def step(*args, **kwargs):
        instance.stop()
        return {'done': activity_done}
    def continue_as_new(_request):
        pytest.fail('stop signal was lost at ContinueAsNew boundary')
    monkeypatch.setattr(workflows.workflow, 'execute_activity', step)
    monkeypatch.setattr(workflows.workflow, 'continue_as_new', continue_as_new)
    request = workflow_request(store.list_outbox()[0], max_steps=max_steps, history_batch=1)
    result = asyncio.run(instance.run(request))
    assert result['outcome']['status'] == 'orchestration_stopped'
