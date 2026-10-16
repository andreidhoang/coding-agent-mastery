"""Recovery plans preserve unknown effects; checkpoint restore never grants authority."""

from __future__ import annotations
from .artifacts import digest_json, canonical_bytes


def recovery_plan(snapshot: dict) -> dict:
    unknowns = [
        d["dispatch_id"] for d in snapshot["dispatches"] if d["effect_state"] in {"in_flight", "unknown"}
    ]
    liabilities = [d["dispatch_id"] for d in snapshot["dispatches"] if d["billing_state"] != "settled"]
    retained = [s["sandbox_id"] for s in snapshot["sandboxes"] if s["status"] != "retired"]
    if snapshot["quarantined"]:
        next_step = "operator_restore_reconciliation"
    elif unknowns:
        next_step = "reconcile_effects_before_replacement"
    elif retained:
        next_step = "confirm_environment_retirement"
    elif snapshot["task"]["execution_state"] in {"cancelled", "review_eligible", "failed"}:
        next_step = "settlement_or_review_only"
    else:
        next_step = "reacquire_owner_then_restore_valid_checkpoint"
    return {
        "schema": 1,
        "next_step": next_step,
        "unknown_dispatches": unknowns,
        "unsettled_dispatches": liabilities,
        "retained_sandboxes": retained,
        "budget": snapshot["budget"],
        "frontier": snapshot["frontier"],
    }


def restore_checkpoint(store, artifacts, tenant_id: str, task_id: str, checkpoint_id: str) -> dict:
    # Typed skills proofs use bounded exact reads, never a whole-task snapshot.
    with store._read() as c:
        row = store._get(c, "checkpoints", checkpoint_id, tenant_id, task_id)
    if type(row["manifest"].get("schema")) is int and row["manifest"]["schema"] == 3:
        from .skill_recovery import restore_skills_checkpoint
        return restore_skills_checkpoint(store, artifacts, tenant_id, task_id, checkpoint_id)
    snapshot = store.snapshot(tenant_id, task_id)
    checkpoint = next((c for c in snapshot["checkpoints"] if c["checkpoint_id"] == checkpoint_id), None)
    if checkpoint is None:
        raise ValueError("checkpoint outside task authority")
    if (
        checkpoint["contract"] != snapshot["task"]["contract"]
        or checkpoint["owner"]["generation"] != snapshot["task"]["generation"]
    ):
        raise ValueError("checkpoint contract/generation is stale")
    old_attempt = checkpoint["owner"]["attempt_id"]
    relevant = [d for d in snapshot["dispatches"] if d["attempt_id"] == old_attempt]
    frontier = checkpoint.get("dispatch_frontier")
    if not isinstance(frontier, list):
        raise ValueError("checkpoint lacks authoritative dispatch frontier")
    if any(
        d["effect_state"] in {"in_flight", "unknown"} or d["dispatch_id"] not in frontier for d in relevant
    ):
        raise ValueError("post-checkpoint effects require explicit reconciliation; cannot rewind")
    if any(d["attempt_id"] == old_attempt for d in checkpoint["pending_dispatches"]):
        raise ValueError("checkpoint contains unresolved effects from its owner attempt")
    manifest = checkpoint["manifest"]
    payload = artifacts.get_json(tenant_id, task_id, manifest["artifact_ref"]["digest"])
    context = None
    if any(k in manifest or k in payload for k in ("kind", "context", "context_schema")) or any(
        "schema" in value and (type(value["schema"]) is not int or value["schema"] != 1)
        for value in (manifest, payload)
    ):
        context = validate_context_checkpoint(artifacts, tenant_id, task_id, manifest, payload)
        accepted_dispatch = next((d for d in relevant if d["dispatch_id"] == context["dispatch_id"]), None)
        if accepted_dispatch is None or not _same(accepted_dispatch.get("context_acceptance"), context["acceptance"]):
            raise ValueError("checkpoint context outside accepted dispatch authority")
        validate_checkpoint_dispatches(context, payload, snapshot["dispatches"], checkpoint["owner"])
    # Historical checkpoints may be untagged minimal payloads. Their existing
    # causal/owner checks above remain authoritative; closed validation belongs
    # only to the explicitly tagged context path, never inferred from absence.
    files = artifacts.get_json(tenant_id, task_id, payload["workspace_ref"]["digest"])
    result = {
        "contract_digest": digest_json(checkpoint["contract"]),
        "messages": payload["messages"],
        "evidence": payload["evidence"],
        "next_turn": manifest["next_turn"],
        "workspace_digest": digest_json(files),
        "files": files,
        "source_checkpoint": checkpoint_id,
        "completion_proposed": payload.get("status") == "completion_proposed",
        "authority": "caller must separately acquire a current owner; this data grants none",
    }
    if context is not None:
        result["context"] = context
    return result


_CONTEXT_MANIFEST_KEYS = set("context_schema strategy projection_ref projection_digest raw_history_ref source_history_digest source_evidence_digest source_workspace_digest request_ref request_digest binding config offload_refs restored_from_projection_id source_checkpoint".split())
_BINDING_KEYS = set("tenant_id task_id generation owner contract_digest source_history_digest source_evidence_digest source_workspace_digest source_frontier expected_previous_projection_id adapter config_digest".split())
_ADAPTER_KEYS = set("provider protocol adapter_version model endpoint system_digest tools_digest continuation_capability".split())
_DESCRIPTOR_KEYS = set("call_id message_index block_index digest size encoding".split())


def _same(left, right):
    return canonical_bytes(left) == canonical_bytes(right)


def _closed(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("invalid closed " + label)


def _context_ref(artifacts, tenant, task, ref):
    from .artifacts import digest_bytes
    from .contracts import digest, strict_int
    _closed(ref, {"tenant_id", "task_id", "digest", "size", "content_type"}, "artifact reference")
    if ref["tenant_id"] != tenant or ref["task_id"] != task:
        raise ValueError("context artifact outside task scope")
    digest(ref["digest"], "artifact digest")
    strict_int(ref["size"], "artifact size")
    data = artifacts.get(tenant, task, ref["digest"])
    if len(data) != ref["size"] or digest_bytes(data) != ref["digest"]:
        raise ValueError("context artifact integrity mismatch")
    return data


def validate_context_manifest(artifacts, tenant, task, manifest):
    """Validate immutable artifact bytes before entering an authority transaction."""
    import json
    from copy import deepcopy
    from .artifacts import canonical_bytes, digest_bytes
    from .contracts import strict_int, validate_owner, digest
    from .context import validate_context_config
    version = manifest.get("context_schema") if isinstance(manifest, dict) else None
    if type(version) is not int or version not in {1, 2}:
        raise ValueError("unknown context schema")
    skills = version == 2
    _closed(manifest, _CONTEXT_MANIFEST_KEYS | (
        {"skills_state_ref", "skills_state_digest", "prompt_digest"} if skills else set()), "context manifest")
    binding = manifest["binding"]
    _closed(binding, _BINDING_KEYS | ({"skills_state_digest"} if skills else set()), "context binding")
    _closed(binding["adapter"], _ADAPTER_KEYS | ({"skills_capability"} if skills else set()), "context adapter")
    from .contracts import OWNER_FIELDS
    _closed(binding["owner"], OWNER_FIELDS, "context owner")
    validate_owner(binding["owner"])
    strict_int(binding["generation"], "context generation", 1)
    _closed(binding["source_frontier"], {"service_incarnation", "sequence"}, "context frontier")
    strict_int(binding["source_frontier"]["sequence"], "context sequence")
    config = validate_context_config(manifest["config"])
    if manifest["strategy"] != config["strategy"] or binding["config_digest"] != digest_json(config):
        raise ValueError("context config identity mismatch")
    for key in ("source_history_digest", "source_evidence_digest", "source_workspace_digest"):
        digest(manifest[key], key)
        if binding[key] != manifest[key]:
            raise ValueError("context source binding mismatch")
    if (binding["tenant_id"] != tenant or binding["task_id"] != task
            or binding["owner"]["tenant_id"] != tenant or binding["owner"]["task_id"] != task
            or binding["owner"]["generation"] != binding["generation"]):
        raise ValueError("context binding scope mismatch")
    source = json.loads(_context_ref(artifacts, tenant, task, manifest["raw_history_ref"]))
    _closed(source, {"schema", "messages", "evidence", "workspace_digest"}, "raw history")
    if type(source["schema"]) is not int or source["schema"] != 1:
        raise ValueError("invalid raw history schema")
    if (digest_json(source["messages"]) != manifest["source_history_digest"]
            or digest_json(source["evidence"]) != manifest["source_evidence_digest"]
            or source["workspace_digest"] != manifest["source_workspace_digest"]):
        raise ValueError("raw source identity mismatch")
    if not isinstance(source["messages"], list) or not isinstance(source["evidence"], list):
        raise ValueError("invalid raw history lists")
    for item in source["evidence"]:
        _closed(item, {"request_ref", "response_ref"}, "source provider evidence")
        _context_ref(artifacts, tenant, task, item["request_ref"])
        _context_ref(artifacts, tenant, task, item["response_ref"])
    projection = json.loads(_context_ref(artifacts, tenant, task, manifest["projection_ref"]))
    _closed(projection, {"schema", "constraints", "messages", "evidence", "binding", "offload_refs"}
            | ({"skills_state_digest"} if skills else set()), "projection")
    if (type(projection["schema"]) is not int or projection["schema"] != version
            or digest_json(projection) != manifest["projection_digest"]
            or manifest["projection_ref"]["digest"] != manifest["projection_digest"]
            or not _same(projection["binding"], binding) or not _same(projection["evidence"], source["evidence"])
            or digest_json(projection["constraints"]) != binding["contract_digest"]):
        raise ValueError("projection identity mismatch")
    if not isinstance(manifest["offload_refs"], list):
        raise ValueError("invalid offload references")
    if [{k: v for k, v in entry.items() if k != "artifact_ref"} for entry in manifest["offload_refs"]
            if isinstance(entry, dict)] != projection["offload_refs"]:
        raise ValueError("manifest/projection offload descriptors differ")
    descriptors = []
    rebuilt = deepcopy(projection["messages"])
    coordinates = set()
    from .protocol import validate_linkage, validate_nebius_linkage
    native = binding["adapter"]["provider"] == "nebius"
    validator = validate_nebius_linkage if native else validate_linkage
    validator(source["messages"])
    validator(projection["messages"])
    batches, calls = [], {}
    for index, message in enumerate(source["messages"]):
        if message.get("role") != "assistant":
            continue
        entries = [(b["id"], b["function"]["name"]) for b in message.get("tool_calls") or []] if native else [
            (b["id"], b["name"]) for b in message.get("content", []) if b.get("type") == "tool_use"
        ] if isinstance(message.get("content"), list) else []
        if entries:
            batches.append(index)
            for call_id, name in entries:
                calls[call_id] = (index, name)
    protected = set(batches[-config["keep_recent_tool_batches"]:])
    for entry in manifest["offload_refs"]:
        _closed(entry, _DESCRIPTOR_KEYS | {"artifact_ref"}, "offload entry")
        descriptor = {k: entry[k] for k in _DESCRIPTOR_KEYS}
        strict_int(entry["message_index"], "message index")
        if entry["block_index"] is not None:
            strict_int(entry["block_index"], "block index")
        coordinate = (entry["message_index"], entry["block_index"])
        if coordinate in coordinates or entry["encoding"] != "utf-8":
            raise ValueError("invalid offload coordinates")
        coordinates.add(coordinate)
        try:
            source_message = source["messages"][entry["message_index"]]
            source_target = source_message if entry["block_index"] is None else source_message["content"][entry["block_index"]]
            source_body = source_target["content"]
            if (not isinstance(source_body, str) or len(source_body.encode("utf-8")) != entry["size"]
                    or digest_bytes(source_body.encode("utf-8")) != entry["digest"]):
                raise ValueError("offload descriptor differs from raw source body")
        except (IndexError, KeyError, TypeError) as exc:
            raise ValueError("invalid offload source coordinate") from exc
        body = _context_ref(artifacts, tenant, task, entry["artifact_ref"])
        if digest_bytes(body) != entry["digest"] or len(body) != entry["size"]:
            raise ValueError("offload descriptor mismatch")
        strict_int(entry["size"], "offload size", 1)
        try:
            message = rebuilt[entry["message_index"]]
            target = message if entry["block_index"] is None else message["content"][entry["block_index"]]
            if ((native and (entry["block_index"] is not None or message.get("role") != "tool"
                            or message.get("tool_call_id") != entry["call_id"]))
                    or (not native and (entry["block_index"] is None or message.get("role") != "user"
                            or target.get("type") != "tool_result" or target.get("tool_use_id") != entry["call_id"]))):
                raise ValueError("offload does not identify a tool result")
            batch, name = calls[entry["call_id"]]
            if (batch in protected or name in ({"read_context_artifact", "load_skill", "read_skill_resource"}
                                                if skills else {"read_context_artifact"})
                    or len(body) <= config["min_offload_bytes"] or config["strategy"] != "tool_result_offload_v1"):
                raise ValueError("offload source is ineligible")
            marker = canonical_bytes({"context_offload": "tool_result_offload_v1", "digest": entry["digest"],
                "size": entry["size"], "tool": "read_context_artifact", "arguments": {
                "digest": entry["digest"], "offset": 0, "limit": config["retrieval_max_bytes"]}}).decode("utf-8")
            if target["content"] != marker:
                raise ValueError("noncanonical offload marker")
            target["content"] = body.decode("utf-8")
        except (IndexError, TypeError, KeyError, UnicodeError) as exc:
            raise ValueError("invalid offload source coordinate") from exc
        descriptors.append(descriptor)
    if descriptors != projection["offload_refs"] or not _same(rebuilt, source["messages"]):
        raise ValueError("projection differs from immutable source")
    if len(canonical_bytes(projection)) > config["max_bytes"]:
        raise ValueError("context projection exceeds configured cap")
    request = json.loads(_context_ref(artifacts, tenant, task, manifest["request_ref"]))
    if digest_json(request) != manifest["request_digest"] or manifest["request_ref"]["digest"] != manifest["request_digest"]:
        raise ValueError("accepted request identity mismatch")
    if skills:
        from .skill_disclosure import validate_state_artifacts
        validated_skills = validate_state_artifacts(artifacts, tenant, task, manifest)
    validate_accepted_request(projection, manifest, request, skills=validated_skills if skills else None)
    if manifest["restored_from_projection_id"] is not None:
        digest(manifest["restored_from_projection_id"], "restore projection")
        digest(manifest["source_checkpoint"], "source checkpoint")
    elif manifest["source_checkpoint"] is not None:
        raise ValueError("partial restore provenance")
    return {"source": source, "projection": projection, "request": request,
            **(validated_skills if skills else {})}


# Closed checkpoint schema 2: base legacy payload fields plus kind/context; authority
# manifest: base legacy fields plus schema/kind/context. Context separates the last
# accepted source prefix from newer raw history produced by that response.
_CONTEXT_CHECKPOINT_KEYS = {"acceptance", "dispatch_id", "source_message_count", "source_evidence_count",
                            "checkpoint_history_digest", "checkpoint_evidence_digest"}


def validate_context_checkpoint(artifacts, tenant, task, manifest, payload):
    from .contracts import strict_int
    skills = isinstance(manifest, dict) and type(manifest.get("schema")) is int and manifest["schema"] == 3
    extra = {"skills_after_turn"} if skills else set()
    _closed(manifest, {"artifact_ref", "workspace_ref", "provider_artifacts", "next_turn",
                      "completion_proposed", "schema", "kind", "context"} | extra, "context checkpoint manifest")
    _closed(payload, {"schema", "kind", "context", "messages", "evidence", "workspace_ref",
                     "projection_version", "status"} | extra, "context checkpoint payload")
    for value in (manifest, payload):
        if (type(value["schema"]) is not int or value["schema"] != (3 if skills else 2)
                or value["kind"] != ("harness_skills_v1" if skills else "harness_context_v1")):
            raise ValueError("unknown context checkpoint schema/kind")
    if (not _same(manifest["context"], payload["context"]) or not _same(manifest["workspace_ref"], payload["workspace_ref"])
            or not _same(manifest["provider_artifacts"], payload["evidence"])
            or manifest["completion_proposed"] != (payload["status"] == "completion_proposed")):
        raise ValueError("checkpoint authority/payload mismatch")
    _context_ref(artifacts, tenant, task, manifest["artifact_ref"])
    _context_ref(artifacts, tenant, task, manifest["workspace_ref"])
    strict_int(manifest["next_turn"], "checkpoint next turn", 1)
    if manifest["next_turn"] != len(payload["evidence"]):
        raise ValueError("checkpoint next turn differs from retained provider evidence")
    if (type(manifest["completion_proposed"]) is not bool
            or type(payload["projection_version"]) is not int or payload["projection_version"] != 1
            or payload["status"] not in {"checkpointed", "completion_proposed"}
            or not isinstance(payload["messages"], list) or not isinstance(payload["evidence"], list)):
        raise ValueError("invalid context checkpoint history metadata")
    context = payload["context"]
    _closed(context, _CONTEXT_CHECKPOINT_KEYS, "checkpoint context")
    acceptance = context["acceptance"]
    _closed(acceptance, {"context_schema", "projection_id", "manifest", "accepted_sequence"}, "context acceptance")
    if type(acceptance["context_schema"]) is not int or acceptance["context_schema"] != (2 if skills else 1):
        raise ValueError("unknown acceptance schema")
    strict_int(acceptance["accepted_sequence"], "accepted sequence", 1)
    if acceptance["projection_id"] != digest_json(acceptance["manifest"]):
        raise ValueError("checkpoint accepted projection identity mismatch")
    validated = validate_context_manifest(artifacts, tenant, task, acceptance["manifest"])
    source = validated["source"]
    strict_int(context["source_message_count"], "source message count")
    strict_int(context["source_evidence_count"], "source evidence count")
    if (context["source_message_count"] != len(source["messages"])
            or context["source_evidence_count"] != len(source["evidence"])
            or not _same(payload["messages"][:context["source_message_count"]], source["messages"])
            or not _same(payload["evidence"][:context["source_evidence_count"]], source["evidence"])
            or digest_json(payload["messages"]) != context["checkpoint_history_digest"]
            or digest_json(payload["evidence"]) != context["checkpoint_evidence_digest"]):
        raise ValueError("checkpoint raw history is not accepted source prefix")
    if not any(item["request_ref"] == acceptance["manifest"]["request_ref"] for item in payload["evidence"]):
        raise ValueError("checkpoint missing accepted request provenance")
    if skills:
        if (not _same(manifest["skills_after_turn"], payload["skills_after_turn"])
                or len(payload["evidence"]) != len(source["evidence"]) + 1
                or payload["evidence"][-1]["request_ref"] != acceptance["manifest"]["request_ref"]):
            raise ValueError("skills checkpoint post-turn identity mismatch")
    return context



def validate_accepted_request(projection, manifest, request, *, skills=None):
    """Rebuild provider bytes from frozen metadata; no network or planner invocation."""
    if manifest["context_schema"] == 2:
        from .skill_disclosure import validate_request
        return validate_request(projection, manifest, request, skills)
    from .providers import AnthropicMessages, NebiusChatCompletions, ScriptedModel, context_capability
    from .protocol import tool_schemas
    from .artifacts import canonical_bytes
    contract = projection["constraints"]
    adapter = manifest["binding"]["adapter"]
    provider = adapter["provider"]
    include_context = manifest["config"]["strategy"] == "tool_result_offload_v1"
    system = "Follow only the frozen task constraints: " + str(contract["requirements"])
    if adapter["model"] != contract["model"] or adapter["adapter_version"] != "context_v1":
        raise ValueError("accepted adapter model/version mismatch")
    if provider == "scripted":
        model = ScriptedModel([])
        expected = {"projection": projection, "digest": manifest["projection_digest"],
                    "bytes": len(canonical_bytes(projection)), "token_count": None,
                    "token_count_status": "provider tokenizer not configured"}
        tools = tool_schemas(include_context=include_context)
        protocol, endpoint = "anthropic", None
    elif provider in {"nebius", "anthropic"}:
        cls = NebiusChatCompletions if provider == "nebius" else AnthropicMessages
        model = cls.__new__(cls)
        model.model = contract["model"]
        endpoint = NebiusChatCompletions.ENDPOINT if provider == "nebius" else None
        model.endpoint = endpoint
        if provider == "anthropic" and include_context:
            raise ValueError("Anthropic offload is unsupported")
        payload = model.build_request(projection["messages"], system,
                                     contract["rate_snapshot"]["max_output_tokens"], include_context=include_context)
        tools = payload["tools"]
        protocol = "chat_completions" if provider == "nebius" else "messages"
        expected = {"provider": "nebius", "protocol": "chat_completions", "endpoint": endpoint,
                    "payload": payload} if provider == "nebius" else payload
        if len(canonical_bytes(payload)) > contract["rate_snapshot"]["max_request_bytes"]:
            raise ValueError("accepted request exceeds frozen provider byte bound")
    else:
        raise ValueError("unsupported context adapter")
    if (adapter["protocol"] != protocol or adapter["endpoint"] != endpoint
            or adapter["system_digest"] != digest_json(system) or adapter["tools_digest"] != digest_json(tools)
            or adapter["continuation_capability"] != context_capability(model) or not _same(request, expected)):
        raise ValueError("accepted request differs from frozen projection/adapter")



def validate_checkpoint_dispatches(context, payload, dispatches, owner):
    accepted = [d for d in dispatches if d["owner"] == owner and "context_acceptance" in d]
    latest = max(accepted, key=lambda d: d["context_acceptance"]["accepted_sequence"]) if accepted else None
    if (latest is None or latest["dispatch_id"] != context["dispatch_id"]
            or not _same(latest["context_acceptance"], context["acceptance"])):
        raise ValueError("checkpoint context is not last accepted owner dispatch")
    by_request = {d["context_acceptance"]["manifest"]["request_ref"]["digest"]: d
                  for d in dispatches if "context_acceptance" in d}
    for item in payload["evidence"]:
        dispatch = by_request.get(item["request_ref"]["digest"])
        if (dispatch is None or dispatch["effect_state"] != "succeeded"
                or dispatch["result_ref"] != item["response_ref"]
                or dispatch["context_acceptance"]["manifest"]["request_ref"] != item["request_ref"]):
            raise ValueError("checkpoint provider evidence differs from accepted dispatch/receipt")
