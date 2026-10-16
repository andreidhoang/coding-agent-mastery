"""Bounded context projection with source digests; no lossy protocol compaction."""

from __future__ import annotations

from .artifacts import canonical_bytes, digest_bytes
from .protocol import validate_linkage, validate_nebius_linkage


def project_context(
    contract: dict, messages: list[dict], evidence: list[dict], max_bytes: int = 131072,
    *, protocol: str = "anthropic",
) -> dict:
    if protocol == "nebius":
        validate_nebius_linkage(messages)
    elif protocol == "anthropic":
        validate_linkage(messages)
    else:
        raise ValueError("unsupported context protocol")
    # Keep protocol artifacts intact. A summary is never a replacement for opaque provider state.
    result = {"schema": 1, "constraints": contract, "messages": messages, "evidence": evidence}
    data = canonical_bytes(result)
    if len(data) > max_bytes:
        raise ValueError("context byte budget exhausted; explicit new-session handoff required")
    return {
        "projection": result,
        "digest": digest_bytes(data),
        "bytes": len(data),
        "token_count": None,
        "token_count_status": "provider tokenizer not configured",
    }


def evidence_is_current(reference: dict, data: bytes) -> bool:
    return reference.get("digest") == digest_bytes(data)


CONFIG_KEYS = {"schema", "strategy", "max_bytes", "min_offload_bytes",
               "keep_recent_tool_batches", "retrieval_max_bytes"}
BINDING_KEYS = {"tenant_id", "task_id", "generation", "owner", "contract_digest",
                "source_history_digest", "source_evidence_digest", "source_workspace_digest",
                "source_frontier", "expected_previous_projection_id", "adapter", "config_digest"}
ADAPTER_KEYS = {"provider", "protocol", "adapter_version", "model", "endpoint",
                "system_digest", "tools_digest", "continuation_capability"}


def default_context_config(max_bytes=131072, strategy="full_history_v1") -> dict:
    config = {"schema": 1, "strategy": strategy, "max_bytes": max_bytes,
              "min_offload_bytes": 1024, "keep_recent_tool_batches": 1,
              "retrieval_max_bytes": 8192}
    return validate_context_config(config)


def validate_context_config(config: dict) -> dict:
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise ValueError("invalid context config fields")
    if type(config["schema"]) is not int or config["schema"] != 1:
        raise ValueError("unsupported context config schema")
    if config["strategy"] not in {"full_history_v1", "tool_result_offload_v1"}:
        raise ValueError("unsupported context strategy")
    for key, cap in (("max_bytes", 8 * 1024 * 1024), ("min_offload_bytes", 8 * 1024 * 1024),
                     ("keep_recent_tool_batches", 64), ("retrieval_max_bytes", 8192)):
        if type(config[key]) is not int or not 1 <= config[key] <= cap:
            raise ValueError("invalid context config bound")
    return _frozen(config)


def _frozen(value):
    import json
    return json.loads(canonical_bytes(value))


def plan_context(contract, messages, evidence, *, binding, config, protocol) -> dict:
    """Pure chronological offloading; projected bytes never replace source authority."""
    from .artifacts import digest_json

    config = validate_context_config(config)
    skills = isinstance(binding, dict) and isinstance(binding.get("adapter"), dict) \
        and binding["adapter"].get("adapter_version") == "context_skills_v1"
    binding_keys = BINDING_KEYS | ({"skills_state_digest"} if skills else set())
    if not isinstance(binding, dict) or set(binding) != binding_keys:
        raise ValueError("invalid context binding fields")
    from .contracts import OWNER_FIELDS, digest, identity, strict_int, validate_owner
    if not isinstance(binding["owner"], dict) or set(binding["owner"]) != set(OWNER_FIELDS):
        raise ValueError("invalid exact owner binding")
    owner = validate_owner(binding["owner"])
    for key in ("tenant_id", "task_id"):
        identity(binding[key], key)
        if binding[key] != owner[key]:
            raise ValueError("owner scope binding mismatch")
    strict_int(binding["generation"], "generation", 1)
    if binding["generation"] != owner["generation"]:
        raise ValueError("owner generation binding mismatch")
    frontier = binding["source_frontier"]
    if not isinstance(frontier, dict) or set(frontier) != {"service_incarnation", "sequence"}:
        raise ValueError("invalid source frontier")
    identity(frontier["service_incarnation"])
    strict_int(frontier["sequence"], "source sequence")
    if frontier["service_incarnation"] != owner["service_incarnation"]:
        raise ValueError("source incarnation mismatch")
    for key in ("contract_digest", "source_history_digest", "source_evidence_digest",
                "source_workspace_digest", "config_digest"):
        digest(binding[key], key)
    if binding["expected_previous_projection_id"] is not None:
        digest(binding["expected_previous_projection_id"])
    adapter = binding["adapter"]
    adapter_keys = ADAPTER_KEYS | ({"skills_capability"} if skills else set())
    if not isinstance(adapter, dict) or set(adapter) != adapter_keys:
        raise ValueError("invalid context adapter fields")
    for key in ("provider", "protocol", "adapter_version", "model", "continuation_capability"):
        if not isinstance(adapter[key], str) or not adapter[key]:
            raise ValueError("invalid adapter identity")
    if adapter["endpoint"] is not None and not isinstance(adapter["endpoint"], str):
        raise ValueError("invalid adapter endpoint")
    digest(adapter["system_digest"])
    digest(adapter["tools_digest"])
    if skills:
        digest(binding["skills_state_digest"])
        from .skill_disclosure import validate_adapter
        validate_adapter(adapter, contract)
    if (binding["contract_digest"] != digest_json(contract)
            or binding["source_history_digest"] != digest_json(messages)
            or binding["source_evidence_digest"] != digest_json(evidence)
            or binding["config_digest"] != digest_json(config)):
        raise ValueError("context source binding mismatch")
    if protocol == "anthropic":
        validator = validate_linkage
    elif protocol == "nebius":
        validator = validate_nebius_linkage
    else:
        raise ValueError("unsupported context protocol")
    validator(messages)
    offloading = config["strategy"] == "tool_result_offload_v1"
    if offloading:
        capability = adapter["continuation_capability"]
        expected = {"anthropic": "scripted_tool_result_offload_v1",
                    "nebius": "nebius_chat_completions_tool_result_offload_v1"}[protocol]
        provider = "scripted" if protocol == "anthropic" else "nebius"
        if capability != expected or adapter["provider"] != provider:
            raise ValueError("adapter does not support context offloading")
        if "read_context_artifact" not in contract.get("capabilities", []):
            raise ValueError("context retrieval capability is required")
    projection = _frozen({"schema": 2 if skills else 1, "constraints": contract, "messages": messages,
                          "evidence": evidence, "binding": binding, "offload_refs": []})
    if skills:
        projection["skills_state_digest"] = binding["skills_state_digest"]
    offloads = []

    def result():
        data = canonical_bytes(projection)
        return {"projection": projection, "digest": digest_bytes(data), "bytes": len(data),
                "token_count": None, "token_count_status": "provider tokenizer not configured",
                "offloads": offloads}

    if len(canonical_bytes(projection)) <= config["max_bytes"]:
        return result()
    if offloading:
        batches, call_batches, names = [], {}, {}
        for index, message in enumerate(messages):
            if message.get("role") != "assistant":
                continue
            if protocol == "nebius":
                calls = [(b["id"], b["function"]["name"]) for b in message.get("tool_calls") or []]
            else:
                calls = [(b["id"], b["name"]) for b in message.get("content", [])
                         if b.get("type") == "tool_use"] if isinstance(message.get("content"), list) else []
            if calls:
                batches.append(index)
                for call_id, name in calls:
                    call_batches[call_id], names[call_id] = index, name
        protected = set(batches[-config["keep_recent_tool_batches"]:])
        for index, message in enumerate(messages):
            if protocol == "nebius":
                bodies = [(None, message["tool_call_id"], message["content"])] \
                    if message.get("role") == "tool" else []
            else:
                bodies = [(j, b["tool_use_id"], b.get("content"))
                          for j, b in enumerate(message.get("content", []))
                          if isinstance(b, dict) and b.get("type") == "tool_result"] \
                    if message.get("role") == "user" and isinstance(message.get("content"), list) else []
            for block, call_id, body in bodies:
                if (not isinstance(body, str) or call_batches[call_id] in protected
                        or names[call_id] in ({"read_context_artifact", "load_skill", "read_skill_resource"}
                                              if skills else {"read_context_artifact"})
                        or len(body.encode("utf-8")) <= config["min_offload_bytes"]):
                    continue
                descriptor = {"call_id": call_id, "message_index": index, "block_index": block,
                              "digest": digest_bytes(body.encode("utf-8")),
                              "size": len(body.encode("utf-8")), "encoding": "utf-8"}
                marker = canonical_bytes({"context_offload": "tool_result_offload_v1",
                                          "digest": descriptor["digest"], "size": descriptor["size"],
                                          "tool": "read_context_artifact", "arguments": {
                                              "digest": descriptor["digest"], "offset": 0,
                                              "limit": config["retrieval_max_bytes"]}}).decode("utf-8")
                target = projection["messages"][index]
                if block is not None:
                    target = target["content"][block]
                before = len(canonical_bytes(projection))
                target["content"] = marker
                projection["offload_refs"].append(descriptor)
                if len(canonical_bytes(projection)) >= before:
                    target["content"] = body
                    projection["offload_refs"].pop()
                    continue
                offloads.append({**descriptor, "body": body})
                if len(canonical_bytes(projection)) <= config["max_bytes"]:
                    validator(projection["messages"])
                    return result()
    raise ValueError("context byte budget exhausted; no supported projection fits")
