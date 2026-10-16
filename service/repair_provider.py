"""Public, immutable operator approval for the supported repair provider.

Evidence is an operator assertion with a source identity, not fetched proof.
Secrets and credential discovery are deliberately outside this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

import httpx

from .artifacts import canonical_bytes
from .billing import ProviderEnvelope
from .contracts import freeze, strict_int
from .providers import NebiusChatCompletions


def _mock_client(client: object) -> bool:
    """Check every HTTPX transport route; a live mount defeats mock isolation.

    HTTPX exposes no public transport inspection API. The pinned 0.28 client
    stores the default route and optional mounts in these two attributes.
    Unknown client implementations fail closed rather than claim isolation.
    """
    return (
        type(client) is httpx.Client
        and isinstance(client._transport, httpx.MockTransport)
        and all(t is None or isinstance(t, httpx.MockTransport) for t in client._mounts.values())
    )


@dataclass(frozen=True, init=False)
class ProviderApproval:
    """Validated public config. Use ``from_dict``; returned dictionaries detach.

    ``matches`` returns False for unsupported adapters or identity/bound drift.
    A mock record requires an explicitly mock-backed client, even when disabled.
    Operator-verified evidence permits opt-in live construction but does not
    establish catalog availability, correctness, or authoritative current prices.
    """

    _canonical: bytes

    FIELDS = frozenset({
        "schema", "provider", "protocol", "endpoint", "model", "rate_snapshot",
        "evidence", "max_response_bytes",
    })

    def __init__(self, *args, **kwargs):
        raise TypeError("construct provider approval using from_dict")

    @classmethod
    def from_dict(cls, value: dict) -> ProviderApproval:
        if not isinstance(value, dict) or set(value) != cls.FIELDS:
            raise ValueError("complete public provider approval required; unknown fields forbidden")
        data = freeze(value)
        strict_int(data["schema"], "approval schema", 1, 1)
        if data["provider"] != "nebius" or data["protocol"] != "chat_completions":
            raise ValueError("unsupported provider or protocol")
        if data["endpoint"] != NebiusChatCompletions.ENDPOINT:
            raise ValueError("unapproved Nebius endpoint")
        model = data["model"]
        if not isinstance(model, str) or re.fullmatch(r"nvidia/[A-Za-z0-9][A-Za-z0-9._-]*", model) is None:
            raise ValueError("exact nvidia/ model identity required")
        envelope = ProviderEnvelope(data["rate_snapshot"], model)
        if envelope.data["cache_read_per_million"] > envelope.data["input_per_million"]:
            raise ValueError("Nebius cache premium envelope is unsupported")
        evidence = data["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != {"kind", "identity"}:
            raise ValueError("exact public evidence kind and identity required")
        if not isinstance(evidence["kind"], str) or evidence["kind"] not in {"mock", "operator-verified"}:
            raise ValueError("unsupported approval evidence kind")
        identity = evidence["identity"]
        if (not isinstance(identity, str) or not identity.strip()
                or identity != identity.strip() or any(ord(c) < 32 for c in identity)
                or not any(marker in identity for marker in (":", "/", ".md", ".json"))):
            raise ValueError("nonempty source-linked evidence identity required")
        strict_int(data["max_response_bytes"], "response byte bound", 1, 2_000_000)
        instance = object.__new__(cls)
        object.__setattr__(instance, "_canonical", canonical_bytes(data))
        return instance

    def as_dict(self) -> dict:
        return json.loads(self._canonical)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self._canonical).hexdigest()

    @property
    def model(self) -> str:
        return self.as_dict()["model"]

    @property
    def rate_snapshot(self) -> dict:
        return self.as_dict()["rate_snapshot"]

    def matches(self, adapter: object) -> bool:
        """Compare exposed identity/bounds without dispatching or reading secrets."""
        if not isinstance(adapter, NebiusChatCompletions):
            return False
        data = self.as_dict()
        if (adapter.model != data["model"] or adapter.endpoint != data["endpoint"]
                or type(adapter.max_bytes) is not int or adapter.max_bytes != data["max_response_bytes"]):
            return False
        for attr, expected in (
            ("provider", data["provider"]), ("protocol", data["protocol"]),
            ("max_output_tokens", data["rate_snapshot"]["max_output_tokens"]),
            ("max_request_bytes", data["rate_snapshot"]["max_request_bytes"]),
        ):
            if hasattr(adapter, attr):
                observed = getattr(adapter, attr)
                if observed != expected or (type(expected) is int and type(observed) is not int):
                    return False
        if isinstance(adapter, _ApprovedNebius) and adapter.approval.digest != self.digest:
            return False
        return data["evidence"]["kind"] != "mock" or _mock_client(adapter.client)

    def build_adapter(
        self, api_key: str, *, enable_network: bool = False, client: httpx.Client | None = None,
    ) -> NebiusChatCompletions:
        """Construct without sending; enabled mocks require explicit isolated HTTPX."""
        if type(enable_network) is not bool:
            raise ValueError("enable_network must be an explicit boolean")
        if self.as_dict()["evidence"]["kind"] == "mock" and not _mock_client(client):
            raise PermissionError("mock approval requires explicit httpx.MockTransport client")
        return _ApprovedNebius(self, api_key, enable_network=enable_network, client=client)


class _ApprovedNebius(NebiusChatCompletions):
    """Native adapter with approval/bound rechecks at the last dispatch boundary."""

    provider = "nebius"
    protocol = "chat_completions"

    def __init__(self, approval: ProviderApproval, api_key: str, **options):
        data = approval.as_dict()
        super().__init__(api_key, data["model"], endpoint=data["endpoint"],
                         max_response_bytes=data["max_response_bytes"], **options)
        self.approval = approval
        self.max_output_tokens = data["rate_snapshot"]["max_output_tokens"]
        self.max_request_bytes = data["rate_snapshot"]["max_request_bytes"]

    def build_request(self, messages: list[dict], system: str, max_tokens: int = 1024) -> dict:
        if not self.approval.matches(self):
            raise PermissionError("provider approval drift")
        strict_int(max_tokens, "approved output cap", 1, self.max_output_tokens)
        payload = super().build_request(messages, system, max_tokens)
        if len(canonical_bytes(payload)) > self.max_request_bytes:
            raise ValueError("approved request byte bound exceeded")
        return payload

    def receive(self, payload: dict) -> bytes:
        if not self.approval.matches(self):
            raise PermissionError("provider approval drift")
        return super().receive(payload)
