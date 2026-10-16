"""Bounded execution/provider regressions for the 2026-10-10 audit."""
import json
from unittest.mock import patch

import httpx
import pytest

from service.artifacts import LocalArtifacts, digest_bytes
from service.billing import ProviderEnvelope
from service.execution import DockerSandbox, Workspace, _acknowledged_process_result, materialize, tree_digest
from service.harness import Harness
from service.protocol import ProtocolError, ToolCall
from service.providers import AnthropicMessages, NebiusChatCompletions, ScriptedModel, parse_anthropic_response
from service.storage import RuntimeStore


IMAGE = 'sha256:' + 'a' * 64
CONTAINER = 'b' * 64


def observation(output=b'', **changes):
    return {'exit_code': 0, 'reason': 'exited', 'output': output,
            'process_group_retired': True, 'truncated': False, **changes}


INCOMPLETE = [
    {'reason': 'timeout'}, {'reason': 'output_limit', 'truncated': True},
    {'process_group_retired': False}, {'truncated': True},
    {'process_group_retired': None}, {'truncated': None},
]


def owned_sandbox():
    sandbox = DockerSandbox(IMAGE)
    sandbox.provisioning_attempted = sandbox.created = True
    sandbox.container_id = CONTAINER
    return sandbox


@pytest.mark.parametrize('missing', ['exit_code', 'reason', 'process_group_retired', 'truncated'])
def test_missing_launcher_evidence_never_counts_as_acknowledged(missing):
    record = observation()
    del record[missing]
    assert not _acknowledged_process_result(record)


@pytest.mark.parametrize('incomplete', INCOMPLETE)
def test_incomplete_name_conflict_cannot_clear_provisioning_state(incomplete):
    sandbox = DockerSandbox(IMAGE)
    record = observation(b'Conflict: name already in use', exit_code=1, **incomplete)
    with patch('service.execution.bounded_process', return_value=record), patch.object(
        sandbox, 'close', side_effect=RuntimeError('uncertain cleanup')
    ):
        with pytest.raises(RuntimeError, match='provisioning/retirement unknown'):
            sandbox.start({'a.py': 'old'})
    assert sandbox.provisioning_attempted and not sandbox.create_rejected


def test_complete_name_conflict_grants_no_removal_authority():
    sandbox = DockerSandbox(IMAGE)
    with patch('service.execution.bounded_process', return_value=observation(
        b'Conflict: name already in use', exit_code=1
    )), patch.object(sandbox, 'close') as close:
        with pytest.raises(RuntimeError, match='Conflict'):
            sandbox.start({'a.py': 'old'})
    assert sandbox.create_rejected and not sandbox.provisioning_attempted
    close.assert_not_called()


@pytest.mark.parametrize('incomplete', INCOMPLETE)
def test_incomplete_inventory_never_releases_owned_instance(incomplete):
    sandbox = owned_sandbox()
    with patch('service.execution.bounded_process', side_effect=[observation(), observation(**incomplete)]):
        with pytest.raises(RuntimeError, match='retirement unknown'):
            sandbox.close()
    assert sandbox.created and sandbox.provisioning_attempted
    assert sandbox.container_id == CONTAINER


@pytest.mark.parametrize('incomplete', INCOMPLETE)
def test_binding_and_nonce_recovery_require_complete_observations(incomplete):
    sandbox = DockerSandbox(IMAGE)
    details = {'Id': CONTAINER, 'Name': '/' + sandbox.name,
               'Config': {'Labels': {'coding-agent-mastery-create-nonce': sandbox.creation_nonce}}}
    with patch('service.execution.bounded_process', return_value=observation(json.dumps(details).encode(), **incomplete)):
        with pytest.raises(RuntimeError, match='ownership unresolved'):
            sandbox._bind_container(CONTAINER)
    assert sandbox.container_id is None
    with patch('service.execution.bounded_process', return_value=observation(CONTAINER.encode(), **incomplete)):
        with pytest.raises(RuntimeError, match='provisioning is unresolved'):
            sandbox._recover_owned_instance()
    assert sandbox.container_id is None


@pytest.mark.parametrize('stage', ['create', 'start', 'copy'])
@pytest.mark.parametrize('incomplete', INCOMPLETE)
def test_provisioning_never_accepts_incomplete_stage(stage, incomplete):
    sandbox = DockerSandbox(IMAGE)
    details = {'Id': CONTAINER, 'Name': '/' + sandbox.name,
               'Config': {'Labels': {'coding-agent-mastery-create-nonce': sandbox.creation_nonce}}}
    records = [observation(CONTAINER.encode()), observation(json.dumps(details).encode()), observation(), observation()]
    index = {'create': 0, 'start': 2, 'copy': 3}[stage]
    records[index].update(incomplete)
    with patch('service.execution.bounded_process', side_effect=records), patch.object(sandbox, 'close') as close:
        with pytest.raises(RuntimeError):
            sandbox.start({'a.py': 'old'})
        close.assert_called_once()


@pytest.mark.parametrize('removal', [observation(exit_code=1), observation(reason='timeout'),
                                    observation(process_group_retired=False)])
def test_complete_absence_can_establish_retirement_after_unacknowledged_remove(removal):
    sandbox = owned_sandbox()
    with patch('service.execution.bounded_process', side_effect=[removal, observation()]):
        result = sandbox.close()
    assert result['retired'] is True and result['removal_acknowledged'] is False
    assert not sandbox.created and not sandbox.provisioning_attempted


def test_complete_owned_nonce_binding_and_removal_are_preserved():
    sandbox = DockerSandbox(IMAGE)
    sandbox.provisioning_attempted = True
    details = {'Id': CONTAINER, 'Name': '/' + sandbox.name,
               'Config': {'Labels': {'coding-agent-mastery-create-nonce': sandbox.creation_nonce}}}
    records = [observation(CONTAINER.encode()), observation(json.dumps(details).encode()), observation(), observation()]
    with patch('service.execution.bounded_process', side_effect=records):
        result = sandbox.close()
    assert result['retired'] is True and result['removal_acknowledged'] is True
    assert result['container_id'] == CONTAINER


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_anthropic_dispatch_overrides_redirect_enabled_client(status):
    requests = []
    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(status, headers={'location': 'https://other-host.invalid/receiver'})
        return httpx.Response(200, json=raw_response())
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        model = AnthropicMessages('synthetic-key', 'pinned-test-model', enable_network=True, client=client)
        with pytest.raises(httpx.HTTPStatusError):
            model.request([{'role': 'user', 'content': 'hello'}], 'policy')
    assert len(requests) == 1
    assert str(requests[0].url) == 'https://api.anthropic.com/v1/messages'


def raw_response(calls=()):
    return {'type': 'message', 'role': 'assistant', 'model': 'pinned-test-model',
            'content': [{'type': 'tool_use', 'id': c.call_id, 'name': c.name, 'input': c.arguments} for c in calls],
            'stop_reason': 'tool_use' if calls else 'end_turn',
            'usage': {'input_tokens': 12, 'output_tokens': 8}}


def runtime(tmp_path):
    rate = {'schema': 1, 'unit': 'micro_usd', 'rate_id': 'synthetic-test-rates', 'model': 'pinned-test-model',
            'input_token_bound': 100, 'max_output_tokens': 100, 'input_per_million': 10000,
            'output_per_million': 20000, 'cache_read_per_million': 1000, 'cache_write_per_million': 15000,
            'bound_evidence': 'synthetic mock bound', 'max_request_bytes': 65536}
    artifacts = LocalArtifacts(tmp_path / 'artifacts')
    store = RuntimeStore('sqlite:///' + str(tmp_path / 'db'), artifacts)
    contract = {'repo_id': 'fixture', 'base_revision': tree_digest({'a.py': 'old'}), 'requirements': ['repair'],
                'model': 'pinned-test-model', 'capabilities': ['read_file', 'replace_text', 'finish'],
                'rate_snapshot': rate}
    task = store.submit('tenant', 'key', contract)
    store.set_graph('tenant', task['task_id'], 1, [{'node_id': 'n'}])
    owner = store.claim('tenant', task['task_id'], 'n', 'claim', 100, 60)['owner']
    materialize(tmp_path / 'workspace', {'a.py': 'old'})
    return store, artifacts, task, owner, Workspace(tmp_path / 'workspace', ['a.py']), rate


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('identity', [None, 'other-model'])
@pytest.mark.parametrize('terminal', [False, True])
def test_live_bad_identity_retains_raw_counters_and_unresolved_charge_without_proposal(
    tmp_path, monkeypatch, native, identity, terminal
):
    store, artifacts, task, owner, workspace, rate = runtime(tmp_path)
    calls = [] if terminal else [ToolCall('write', 'replace_text', {'path': 'a.py', 'expected_digest': digest_bytes(b'old'),
                                                                 'old': 'old', 'new': 'new'})]
    raw = raw_response(calls)
    if native:
        raw = {'object': 'chat.completion', 'model': 'pinned-test-model', 'choices': [{
            'index': 0, 'finish_reason': 'tool_calls' if calls else 'stop',
            'message': {'role': 'assistant', 'content': None if calls else 'done',
                        'tool_calls': [{'type': 'function', 'id': c.call_id,
                                        'function': {'name': c.name, 'arguments': json.dumps(c.arguments)}}
                                       for c in calls]}}],
               'usage': {'prompt_tokens': 12, 'completion_tokens': 8, 'total_tokens': 20}}
    if identity is None:
        del raw['model']
    else:
        raw['model'] = identity
    body = json.dumps(raw, indent=2).encode() + b'\n'
    requests = []
    charge_calls = []
    original_charge = ProviderEnvelope.charge
    def charge(envelope, usage):
        charge_calls.append(usage)
        return original_charge(envelope, usage)
    monkeypatch.setattr(ProviderEnvelope, 'charge', charge)
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=body)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = NebiusChatCompletions if native else AnthropicMessages
        model = adapter('synthetic-key', 'pinned-test-model', enable_network=True, client=client)
        harness = Harness(store, artifacts, provider_envelopes={model.model: rate})
        for _ in range(2):
            with pytest.raises(ProtocolError, match='model identity'):
                harness.run(owner, task['contract'], workspace, model)
    state = store.snapshot('tenant', task['task_id'])
    assert len(requests) == len(state['dispatches']) == 1
    receipt = state['dispatches'][0]
    assert receipt['effect_state'] == 'succeeded' and receipt['billing_state'] == 'liability_unknown'
    assert receipt['actual_units'] is None
    assert state['budget']['spent'] == 0 and state['budget']['reserved'] == 100
    assert not charge_calls
    assert artifacts.get('tenant', task['task_id'], receipt['result_ref']['digest']) == body
    assert workspace.snapshot() == {'a.py': 'old'} and state['checkpoints'] == []


@pytest.mark.parametrize('identity', [None, 'other-model'])
def test_anthropic_convenience_parser_enforces_exact_model(identity):
    raw = raw_response()
    if identity is None:
        del raw['model']
    else:
        raw['model'] = identity
    # Offline parser remains compatible when expected identity is omitted.
    assert parse_anthropic_response(raw).terminal
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=raw))) as client:
        model = AnthropicMessages('synthetic-key', 'pinned-test-model', enable_network=True, client=client)
        with pytest.raises(ProtocolError, match='model identity'):
            model.request([{'role': 'user', 'content': 'hello'}], 'policy')


@pytest.mark.parametrize('live', [False, True])
@pytest.mark.parametrize('reused_name', ['read_file', 'finish'])
def test_entire_batch_rejects_reused_id_before_fresh_edit_on_final_turn(tmp_path, live, reused_name):
    store, artifacts, task, owner, workspace, rate = runtime(tmp_path)
    first = [ToolCall('repeat', 'read_file', {'path': 'a.py'})]
    reused_args = {'path': 'a.py'} if reused_name == 'read_file' else {'summary': 'done'}
    second = [ToolCall('new', 'replace_text', {'path': 'a.py', 'expected_digest': digest_bytes(b'old'),
                                             'old': 'old', 'new': 'new'}), ToolCall('repeat', reused_name, reused_args)]
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=raw_response(first if len(requests) == 1 else second))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = (AnthropicMessages('synthetic-key', 'pinned-test-model', enable_network=True, client=client)
                 if live else ScriptedModel([first, second]))
        harness = Harness(store, artifacts, max_turns=2, provider_envelopes={'pinned-test-model': rate})
        for _ in range(2):
            with pytest.raises(ProtocolError, match='duplicate'):
                harness.run(owner, task['contract'], workspace, model)
    state = store.snapshot('tenant', task['task_id'])
    assert workspace.snapshot() == {'a.py': 'old'}
    assert len(state['checkpoints']) == 1
    assert sorted(d['kind'] for d in state['dispatches']) == sorted([
        'model.anthropic' if live else 'model.scripted', 'read_file',
        'model.anthropic' if live else 'model.scripted'])
    assert all(d['result_ref'] for d in state['dispatches'])
    assert len(requests) == (2 if live else 0)


@pytest.mark.parametrize('live', [False, True])
def test_valid_multi_call_batch_can_edit_and_finish(tmp_path, live):
    store, artifacts, task, owner, workspace, rate = runtime(tmp_path)
    calls = [ToolCall('write', 'replace_text', {'path': 'a.py', 'expected_digest': digest_bytes(b'old'),
                                              'old': 'old', 'new': 'new'}), ToolCall('finish', 'finish', {'summary': 'done'})]
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=raw_response(calls)))) as client:
        model = (AnthropicMessages('synthetic-key', 'pinned-test-model', enable_network=True, client=client)
                 if live else ScriptedModel([calls]))
        result = Harness(store, artifacts, max_turns=1, provider_envelopes={'pinned-test-model': rate}).run(
            owner, task['contract'], workspace, model)
    assert result['status'] == 'completion_proposed' and workspace.snapshot() == {'a.py': 'new'}
