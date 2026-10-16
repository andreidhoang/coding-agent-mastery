"""Offline broker load evidence; this profile grants no accepted disclosure authority."""
from __future__ import annotations

from copy import deepcopy

from .artifacts import canonical_bytes, digest_bytes, digest_json
from .contracts import Conflict, digest, identity, validate_owner
from .protocol import ToolCall, strict_json, validate_linkage
from .skills import LIMITS, SkillError, read_catalog_snapshot, _path

SKILL_TOOLS = frozenset({"load_skill", "read_skill_resource"})
_CALL_KEYS = {"schema", "operation", "catalog_digest", "package_digest", "path",
              "source_model_dispatch_id", "source_projection_id", "source_accepted_sequence"}
_RECEIPT_KEYS = {"dispatch_id", "receipt_id", "effect_state", "actual_units", "result_ref"}


def _reject(code="invalid_package"):
    raise SkillError(code) from None


def validate_skill_call(value):
    try:
        if not isinstance(value, dict) or set(value) != _CALL_KEYS:
            _reject()
        if type(value["schema"]) is not int or value["schema"] != 1:
            _reject("unsupported_profile")
        if value["operation"] not in {"load", "read_resource"}:
            _reject()
        for key in ("catalog_digest", "package_digest", "source_projection_id"):
            digest(value[key])
        identity(value["source_model_dispatch_id"])
        if type(value["source_accepted_sequence"]) is not int or value["source_accepted_sequence"] < 1:
            _reject()
        if (value["operation"] == "load" and value["path"] is not None
                or value["operation"] == "read_resource" and not isinstance(value["path"], str)):
            _reject()
        if value["operation"] == "read_resource":
            _path(value["path"])
        return deepcopy(value)
    except SkillError:
        raise
    except (ValueError, TypeError, KeyError):
        _reject()


def _receipt(dispatch, receipts):
    receipt_id = dispatch.get("receipt_id")
    matches = [r for r in receipts if r.get("receipt_id") == receipt_id] if receipt_id else []
    if len(matches) != 1:
        _reject()
    expected = {key: dispatch[key] for key in _RECEIPT_KEYS}
    if set(matches[0]) != _RECEIPT_KEYS or canonical_bytes(matches[0]) != canonical_bytes(expected):
        _reject()
    return matches[0]


def _parameters(dispatch):
    keys = {"owner", "action_id", "dispatch_id", "kind", "input_digest", "bound_units"}
    if canonical_bytes(dispatch.get("parameters")) != canonical_bytes({k: dispatch[k] for k in keys}):
        _reject()


def validate_source_record(source, receipts, owner, metadata, contract):
    """Durable-only source checks, safe to repeat under the store writer lock."""
    try:
        if (source is None or source["owner"] != owner or source["attempt_id"] != owner["attempt_id"]
                or source["tenant_id"] != owner["tenant_id"] or source["task_id"] != owner["task_id"]
                or source["kind"] != "model.scripted" or source["effect_state"] != "succeeded"
                or source["billing_state"] != "settled" or type(source["actual_units"]) is not int
                or source["actual_units"] != 0 or not source["result_ref"]):
            _reject()
        _receipt(source, receipts)
        _parameters(source)
        accepted = source["context_acceptance"]
        manifest = accepted["manifest"]
        binding = manifest["binding"]
        adapter = binding["adapter"]
        if (set(accepted) != {"context_schema", "projection_id", "manifest", "accepted_sequence"}
                or type(accepted["context_schema"]) is not int or accepted["context_schema"] != 1
                or accepted["projection_id"] != digest_json(manifest)
                or source["input_digest"] != manifest["request_digest"]
                or binding["owner"] != owner or binding["contract_digest"] != digest_json(contract)
                or adapter["provider"] != "scripted" or adapter["adapter_version"] != "context_v1"
                or source["dispatch_id"] != metadata["source_model_dispatch_id"]
                or accepted["projection_id"] != metadata["source_projection_id"]
                or type(accepted["accepted_sequence"]) is not int
                or accepted["accepted_sequence"] != metadata["source_accepted_sequence"]):
            _reject()
        return source
    except SkillError:
        raise
    except (KeyError, TypeError, ValueError):
        _reject()


def _read(artifacts, owner, ref, cap, content_type="application/json"):
    try:
        if (not isinstance(ref, dict) or set(ref) != {"tenant_id", "task_id", "digest", "size", "content_type"}
                or ref["tenant_id"] != owner["tenant_id"] or ref["task_id"] != owner["task_id"]
                or ref["content_type"] != content_type or type(ref["size"]) is not int
                or not 0 <= ref["size"] <= cap):
            _reject()
        digest(ref["digest"])
        raw = artifacts.get(owner["tenant_id"], owner["task_id"], ref["digest"], max_bytes=cap)
        if len(raw) != ref["size"] or digest_bytes(raw) != ref["digest"]:
            _reject()
        return raw
    except SkillError:
        raise
    except (ValueError, OSError, TypeError, KeyError):
        _reject()


def _source_calls(artifacts, records, metadata):
    from .providers import decode_provider_payload, parse_anthropic_response
    from .recovery import validate_context_manifest
    try:
        owner = records["owner"]
        source = next((d for d in records["dispatches"]
                       if d["dispatch_id"] == metadata["source_model_dispatch_id"]), None)
        validate_source_record(source, records["receipts"], owner, metadata, records["contract"])
        manifest = source["context_acceptance"]["manifest"]
        validated = validate_context_manifest(artifacts, owner["tenant_id"], owner["task_id"], manifest)
        raw = decode_provider_payload(_read(artifacts, owner, source["result_ref"], 2_000_000))
        response = parse_anthropic_response(raw, "scripted-fixture-v1")
        assistant = {"role": "assistant", "content": response.raw["content"]}
        placeholders = {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call.call_id, "content": ""} for call in response.calls
        ]}
        validate_linkage(validated["source"]["messages"] + [assistant] + ([placeholders] if response.calls else []))
        return response.calls
    except SkillError:
        raise
    except (ValueError, KeyError, TypeError, OSError):
        _reject()


def _matching_call(artifacts, records, dispatch, metadata):
    calls = _source_calls(artifacts, records, metadata)
    candidates = []
    for call in calls:
        call_identity = digest_json({"attempt": records["owner"]["attempt_id"], "call": call.call_id})[:32]
        if dispatch["dispatch_id"] == "dispatch-" + call_identity:
            candidates.append(call)
    if len(candidates) != 1:
        _reject()
    call = candidates[0]
    call_identity = digest_json({"attempt": records["owner"]["attempt_id"], "call": call.call_id})[:32]
    expected_kind = "load_skill" if metadata["operation"] == "load" else "read_skill_resource"
    if (call.name != expected_kind or dispatch["kind"] != expected_kind
            or dispatch["action_id"] != "action-" + call_identity
            or dispatch["input_digest"] != digest_json({"call_digest": call.digest, "skill_call": metadata})
            or call.arguments["catalog_digest"] != metadata["catalog_digest"]
            or call.arguments["package_digest"] != metadata["package_digest"]
            or (call.arguments.get("path") if call.name == "read_skill_resource" else None) != metadata["path"]):
        _reject()
    return call


def _result(snapshot, capture, call, metadata, primary=None):
    package = snapshot["packages"][0]
    error = None
    if call.arguments["package_digest"] != package["package_digest"]:
        error = "invalid_package" if call.name == "load_skill" else "resource_denied"
    elif call.name == "read_skill_resource":
        error = "not_disclosed"
    if error:
        result = {"call_id": call.call_id, "tool": call.name, "ok": False,
                  "error_type": "SkillError", "message": error, "skill_provenance": metadata}
    else:
        if primary is not None:
            value = {"schema": 1, "status": "already_loaded", "catalog_digest": capture["catalog_digest"],
                     "package_digest": package["package_digest"], "load_dispatch_id": primary["load_dispatch_id"]}
        else:
            manifest = package["manifest"]
            value = {"schema": 1, "status": "loaded", "catalog_digest": capture["catalog_digest"],
                     "package_digest": package["package_digest"], "body": package["body"].decode("utf-8"),
                     "body_digest": manifest["body_ref"]["digest"],
                     "resources": [{"path": r["path"], "digest": r["artifact_ref"]["digest"],
                                    "size": r["artifact_ref"]["size"]} for r in manifest["resources"]],
                     "source_model_dispatch_id": metadata["source_model_dispatch_id"]}
        result = {"call_id": call.call_id, "tool": call.name, "ok": True, "value": value,
                  "skill_provenance": metadata}
    if len(canonical_bytes(result)) > LIMITS["max_result_bytes"]:
        _reject("bounds_exceeded")
    return result


def _derive(artifacts, records, capture, config):
    owner = records["owner"]
    if any(d.get("context_acceptance", {}).get("context_schema") == 2 for d in records["dispatches"]):
        _reject("unsupported_profile")
    snapshot = read_catalog_snapshot(artifacts, owner["tenant_id"], owner["task_id"], capture, config)
    loaded, successes = [], []
    try:
        for dispatch in records["dispatches"]:
            if dispatch["kind"] not in SKILL_TOOLS and "skill_call" not in dispatch:
                continue
            metadata = validate_skill_call(dispatch["skill_call"])
            _parameters(dispatch)
            if (metadata["catalog_digest"] != capture["catalog_digest"] or dispatch["owner"] != owner
                    or dispatch["tenant_id"] != owner["tenant_id"] or dispatch["task_id"] != owner["task_id"]
                    or dispatch["attempt_id"] != owner["attempt_id"] or dispatch["bound_units"] != 0
                    or type(dispatch["bound_units"]) is not int):
                _reject()
            call = _matching_call(artifacts, records, dispatch, metadata)
            if dispatch["effect_state"] not in {"in_flight", "unknown", "not_dispatched", "succeeded", "failed_known"}:
                _reject()
            if dispatch["actual_units"] is not None and (type(dispatch["actual_units"]) is not int
                                                         or dispatch["actual_units"] != 0):
                _reject()
            if dispatch["receipt_id"] is not None:
                _receipt(dispatch, records["receipts"])
            elif dispatch["effect_state"] != "in_flight":
                _reject()
            if dispatch["effect_state"] == "in_flight" and (
                    dispatch["receipt_id"] is not None or dispatch["result_ref"] is not None
                    or dispatch["actual_units"] is not None or dispatch["billing_state"] != "reserved"):
                _reject()
            if dispatch["effect_state"] in {"in_flight", "unknown", "not_dispatched"}:
                continue
            if (dispatch["effect_state"] not in {"succeeded", "failed_known"}
                    or dispatch["billing_state"] != "settled" or type(dispatch["actual_units"]) is not int
                    or dispatch["actual_units"] != 0 or not dispatch["result_ref"]):
                _reject()
            raw = _read(artifacts, owner, dispatch["result_ref"], LIMITS["max_result_bytes"])
            result = strict_json(raw.decode("utf-8"), LIMITS["max_result_bytes"])
            if not isinstance(result, dict) or canonical_bytes(result) != raw:
                _reject()
            if dispatch["effect_state"] == "failed_known":
                expected = _result(snapshot, capture, call, metadata)
                if expected["ok"] or canonical_bytes(expected) != raw:
                    _reject()
            else:
                if call.name != "load_skill" or not result.get("ok") or not isinstance(result.get("value"), dict):
                    _reject()
                status = result["value"].get("status")
                if status == "loaded":
                    if canonical_bytes(_result(snapshot, capture, call, metadata)) != raw:
                        _reject()
                    loaded.append({"package_digest": metadata["package_digest"],
                                   "load_dispatch_id": dispatch["dispatch_id"], "result_ref": dispatch["result_ref"]})
                elif status == "already_loaded":
                    successes.append((call, metadata, raw))
                else:
                    _reject()
        if len(loaded) > 1 or successes and len(loaded) != 1:
            _reject()
        for call, metadata, raw in successes:
            if canonical_bytes(_result(snapshot, capture, call, metadata, loaded[0])) != raw:
                _reject()
        state = {"schema": 1, "kind": "broker_skill_loads_v1", **deepcopy(capture),
                 "loaded": loaded, "source_checkpoint": None}
        return state, snapshot
    except SkillError:
        raise
    except (ValueError, KeyError, TypeError, UnicodeError):
        _reject()


def derive_loaded_skills(store, artifacts, owner, capture, config):
    """Describe committed current-attempt loads without granting execution permission."""
    records = store.read_skill_records(validate_owner(owner))
    state, _ = _derive(artifacts, records, capture, config)
    return deepcopy(state)


def _known_result(broker, call, dispatch_id):
    records = broker.store.read_skill_records(broker.owner)
    _derive(broker.artifacts, records, broker.skills_capture, broker.skills_config)
    existing = next((d for d in records["dispatches"] if d["dispatch_id"] == dispatch_id), None)
    if existing is None:
        _reject()
    metadata = validate_skill_call(existing.get("skill_call"))
    if existing["input_digest"] != digest_json({"call_digest": call.digest, "skill_call": metadata}):
        raise Conflict("dispatch ID binds a different skill call")
    if existing["effect_state"] not in {"succeeded", "failed_known"} or not existing["result_ref"]:
        raise RuntimeError("unresolved duplicate skill dispatch requires reconciliation")
    return strict_json(_read(broker.artifacts, broker.owner, existing["result_ref"],
                            LIMITS["max_result_bytes"]).decode("utf-8"), LIMITS["max_result_bytes"])


def execute_skill(broker, call):
    """Prepare, commit intent, publish result, then commit its ordinary receipt."""
    call = ToolCall(call.call_id, call.name, deepcopy(call.arguments))
    owner = broker.owner
    records = broker.store.read_skill_records(owner)
    if not SKILL_TOOLS <= broker.capabilities or not SKILL_TOOLS <= set(records["contract"]["capabilities"]):
        raise PermissionError("skills require both frozen capabilities")
    capture, config = broker.skills_capture, broker.skills_config
    state, snapshot = _derive(broker.artifacts, records, capture, config)
    key = digest_json({"attempt": owner["attempt_id"], "call": call.call_id})[:32]
    dispatch_id, action_id = "dispatch-" + key, "action-" + key
    existing = next((d for d in records["dispatches"] if d["dispatch_id"] == dispatch_id), None)
    if existing is not None:
        metadata = validate_skill_call(existing.get("skill_call"))
        if existing["input_digest"] != digest_json({"call_digest": call.digest, "skill_call": metadata}):
            raise Conflict("dispatch ID binds a different skill call")
        if existing["effect_state"] not in {"succeeded", "failed_known"} or not existing["result_ref"]:
            raise RuntimeError("unresolved duplicate skill dispatch requires reconciliation")
        broker.store.begin_skill_dispatch(owner, action_id, dispatch_id, call.digest, metadata, records["frontier"])
        return _known_result(broker, call, dispatch_id)
    if call.arguments["catalog_digest"] != capture["catalog_digest"]:
        _reject("stale_catalog")
    accepted = broker.context_acceptance
    if accepted is None or broker.context_dispatch_id is None:
        raise PermissionError("skills require a pinned accepted source")
    metadata = validate_skill_call({"schema": 1, "operation": "load" if call.name == "load_skill" else "read_resource",
        "catalog_digest": call.arguments["catalog_digest"], "package_digest": call.arguments["package_digest"],
        "path": call.arguments.get("path"), "source_model_dispatch_id": broker.context_dispatch_id,
        "source_projection_id": accepted["projection_id"], "source_accepted_sequence": accepted["accepted_sequence"]})
    calls = _source_calls(broker.artifacts, records, metadata)
    if sum(c.digest == call.digest for c in calls) != 1:
        raise PermissionError("skill call absent from source response")
    primary = state["loaded"][0] if state["loaded"] else None
    result = _result(snapshot, capture, call, metadata, primary)
    dispatch = broker.store.begin_skill_dispatch(owner, action_id, dispatch_id, call.digest, metadata, records["frontier"])
    if dispatch["duplicate"]:
        return _known_result(broker, call, dispatch_id)
    ref = broker.artifacts.put_json(owner["tenant_id"], owner["task_id"], result)
    broker.store.finish_dispatch(owner["tenant_id"], dispatch_id, "receipt-" + key,
                                 "succeeded" if result["ok"] else "failed_known", 0, ref)
    return deepcopy(result)
