"""Approval controls use synthetic rates and mock transport, never live inference."""

import copy
from dataclasses import FrozenInstanceError

import httpx
import pytest

from service.artifacts import digest_json
from service.billing import ProviderEnvelope
from service.providers import AnthropicMessages, NebiusChatCompletions
from service.repair_provider import ProviderApproval


MODEL = "nvidia/Nemotron-fixture"


def config():
    return {
        "schema": 1, "provider": "nebius", "protocol": "chat_completions",
        "endpoint": NebiusChatCompletions.ENDPOINT, "model": MODEL,
        "rate_snapshot": {
            "schema": 1, "unit": "micro_usd", "rate_id": "mock:rates-v1", "model": MODEL,
            "input_token_bound": 100, "max_output_tokens": 100,
            "input_per_million": 10_000, "output_per_million": 20_000,
            "cache_read_per_million": 1_000, "cache_write_per_million": 15_000,
            "bound_evidence": "mock:bound-v1", "max_request_bytes": 65536,
        },
        "evidence": {"kind": "mock", "identity": "tests/test_repair_provider.py#synthetic-only"},
        "max_response_bytes": 65536,
    }


def mock_client(calls=None, **options):
    def handle(request):
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json={"synthetic": True})
    return httpx.Client(transport=httpx.MockTransport(handle), **options)


def test_canonical_detached_approval_and_native_adapter():
    source = config()
    approval = ProviderApproval.from_dict(source)
    expected = copy.deepcopy(source)
    source["rate_snapshot"]["input_per_million"] = 99
    source["evidence"]["identity"] = "changed:source"
    exported = approval.as_dict()
    exported["evidence"]["kind"] = "operator-verified"
    rates = approval.rate_snapshot
    rates["max_output_tokens"] = 4
    assert approval.as_dict() == expected
    assert approval.rate_snapshot["max_output_tokens"] == 100
    assert approval.model == MODEL
    assert approval.digest == digest_json(expected)
    assert approval.digest == ProviderApproval.from_dict(dict(reversed(list(expected.items())))).digest
    assert ProviderEnvelope(approval.rate_snapshot, approval.model).bound_units > 0
    with pytest.raises(FrozenInstanceError):
        approval._canonical = b"{}"
    with pytest.raises(TypeError, match="from_dict"):
        ProviderApproval(b"{}")
    with mock_client() as client:
        adapter = approval.build_adapter("not-a-real-key", enable_network=True, client=client)
        assert isinstance(adapter, NebiusChatCompletions)
        assert adapter.enabled and approval.matches(adapter)
        assert "not-a-real-key" not in str(approval.as_dict())
        assert adapter.max_output_tokens == 100


@pytest.mark.parametrize("field,value", [
    ("schema", True), ("schema", 2), ("provider", "anthropic"),
    ("protocol", "messages"), ("model", "NVIDIA/Nemotron-fixture"),
    ("model", "nvidia/"), ("model", "nvidia/fixture "), ("model", "nvidia/a/b"),
    ("endpoint", "https://api.tokenfactory.nebius.com/v1/chat/completions"),
    ("endpoint", "https://api.tokenfactory.us-central1.nebius.com/v1/"),
    ("endpoint", "https://evil.invalid/v1/"), ("endpoint", "http://api.tokenfactory.nebius.com/v1/"),
    ("max_response_bytes", True), ("max_response_bytes", 0), ("max_response_bytes", 2_000_001),
    ("max_response_bytes", "10"),
])
def test_invalid_identity_and_bounds(field, value):
    data = config()
    data[field] = value
    with pytest.raises(ValueError):
        ProviderApproval.from_dict(data)


@pytest.mark.parametrize("field,value", [
    ("model", "nvidia/another-model"), ("schema", True), ("unit", "USD"),
    ("cache_read_per_million", 10_001), ("max_output_tokens", 32769),
    ("input_token_bound", 0), ("max_request_bytes", True),
    ("rate_id", ""), ("bound_evidence", ""), ("output_per_million", -1),
])
def test_invalid_rate_envelope(field, value):
    data = config()
    data["rate_snapshot"][field] = value
    with pytest.raises(ValueError):
        ProviderApproval.from_dict(data)


@pytest.mark.parametrize("target", ["root", "rate_snapshot", "evidence"])
@pytest.mark.parametrize("field", ["api_key", "token", "unknown"])
def test_unknown_and_secret_fields_rejected(target, field):
    data = config()
    selected = data if target == "root" else data[target]
    selected[field] = "must-not-persist"
    with pytest.raises(ValueError):
        ProviderApproval.from_dict(data)


@pytest.mark.parametrize("target", ["root", "rate_snapshot", "evidence"])
def test_missing_fields_have_no_defaults(target):
    data = config()
    selected = data if target == "root" else data[target]
    selected.pop(next(iter(selected)))
    with pytest.raises(ValueError):
        ProviderApproval.from_dict(data)


@pytest.mark.parametrize("evidence", [
    None, {"kind": "live", "identity": "catalog:1"}, {"kind": "mock", "identity": ""},
    {"kind": "mock", "identity": "unlinked"}, {"kind": "mock", "identity": " : "},
    {"kind": "mock", "identity": "catalog:\nsecret"},
    {"kind": [], "identity": "catalog:1"}, {"kind": "mock", "identity": None},
])
def test_invalid_evidence(evidence):
    data = config()
    data["evidence"] = evidence
    with pytest.raises(ValueError):
        ProviderApproval.from_dict(data)


def test_mock_approval_denies_implicit_and_live_client_without_dispatch():
    approval = ProviderApproval.from_dict(config())
    for enabled in (False, True):
        with pytest.raises(PermissionError, match="MockTransport"):
            approval.build_adapter("server-held", enable_network=enabled)
        with httpx.Client(trust_env=False) as live:
            with pytest.raises(PermissionError, match="MockTransport"):
                approval.build_adapter("server-held", enable_network=enabled, client=live)
    with mock_client(mounts={"https://": httpx.HTTPTransport()}) as mixed:
        with pytest.raises(PermissionError, match="MockTransport"):
            approval.build_adapter("server-held", enable_network=True, client=mixed)


def test_operator_assertion_enables_explicit_live_construction_without_fetch(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("approval construction must not send HTTP or read credentials")
    monkeypatch.setattr(httpx.Client, "send", unexpected)
    data = config()
    data["evidence"] = {"kind": "operator-verified", "identity": "research/account-catalog.json#approval"}
    approval = ProviderApproval.from_dict(data)
    adapter = approval.build_adapter("server-held")
    try:
        assert not adapter.enabled and approval.matches(adapter)
        with pytest.raises(PermissionError, match="disabled"):
            adapter.receive({})
    finally:
        adapter.client.close()
    adapter = approval.build_adapter("server-held", enable_network=True)
    assert adapter.enabled and approval.matches(adapter)
    adapter.client.close()


@pytest.mark.parametrize("attr,value", [
    ("model", "nvidia/another"), ("endpoint", "https://evil.invalid/"),
    ("max_bytes", 3), ("max_output_tokens", 5), ("max_request_bytes", 2),
    ("provider", "other"), ("protocol", "other"),
])
def test_adapter_drift_is_detected_before_send(attr, value):
    approval = ProviderApproval.from_dict(config())
    calls = []
    with mock_client(calls) as client:
        adapter = approval.build_adapter("server-held", enable_network=True, client=client)
        payload = adapter.build_request([], "mock instruction", 50)
        setattr(adapter, attr, value)
        assert not approval.matches(adapter)
        with pytest.raises(PermissionError, match="drift"):
            adapter.receive(payload)
        assert not calls


def test_transport_and_approval_drift_are_detected_before_send():
    approval = ProviderApproval.from_dict(config())
    changed = config()
    changed["rate_snapshot"]["input_per_million"] += 1
    other = ProviderApproval.from_dict(changed)
    with mock_client() as client:
        adapter = approval.build_adapter("server-held", enable_network=True, client=client)
        assert not other.matches(adapter)
        with httpx.Client(trust_env=False) as live:
            adapter.client = live
            assert not approval.matches(adapter)
            with pytest.raises(PermissionError, match="drift"):
                adapter.receive({})


def test_output_and_request_bounds_are_enforced_and_one_mock_request_is_sent():
    approval = ProviderApproval.from_dict(config())
    calls = []
    with mock_client(calls) as client:
        adapter = approval.build_adapter("server-held", enable_network=True, client=client)
        with pytest.raises(ValueError, match="output cap"):
            adapter.build_request([], "instruction", 101)
        with pytest.raises(ValueError, match="byte bound"):
            adapter.build_request([], "x" * 65536, 100)
        payload = adapter.build_request([], "instruction", 100)
        assert adapter.receive(payload) == b'{"synthetic":true}'
        assert len(calls) == 1
        assert str(calls[0].url) == NebiusChatCompletions.ENDPOINT + "chat/completions"


def test_native_external_adapter_matching_and_wrong_protocol():
    approval = ProviderApproval.from_dict(config())
    with mock_client() as client:
        native = NebiusChatCompletions("server-held", MODEL, client=client, max_response_bytes=65536)
        assert approval.matches(native)
        native.model = "nvidia/nemotron-fixture"
        assert not approval.matches(native)  # exact capitalization is part of identity
        anthropic = AnthropicMessages("server-held", MODEL, client=client)
        assert not approval.matches(anthropic)
        assert not approval.matches(object())


@pytest.mark.parametrize("key,enabled", [("", False), (None, True), ("server-held", 1)])
def test_key_and_explicit_boolean_required(key, enabled):
    approval = ProviderApproval.from_dict(config())
    with mock_client() as client, pytest.raises(ValueError):
        approval.build_adapter(key, enable_network=enabled, client=client)
