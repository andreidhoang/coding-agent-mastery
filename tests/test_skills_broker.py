"""Independent step-3 tests: real scoped receipts, no provider/disclosure claims."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import traceback
from types import SimpleNamespace

import pytest

from service.artifacts import LocalArtifacts, digest_json
from service.context import default_context_config, plan_context
from service.contracts import RuntimeErrorBase
from service.execution import Workspace, materialize, tree_digest
from service.harness import ToolBroker
from service.protocol import ProtocolError, ToolCall, tool_schemas
from service.providers import ScriptedModel, context_capability
from service.skills import capture_skill_catalog, default_skills_config, read_catalog_snapshot, SkillError
from service.storage import RuntimeStore


ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ["load_skill", "read_skill_resource", "finish"]
REJECTIONS = (ValueError, PermissionError, RuntimeError, RuntimeErrorBase)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def case(tmp_path, *, capabilities=None, body=None, url=None):
    artifacts = LocalArtifacts(tmp_path / "artifacts")
    store = RuntimeStore(url or "sqlite:///" + str(tmp_path / "runtime.db"), artifacts)
    files = {"a.txt": "unmodified"}
    task = store.submit("broker-tenant", "broker-case", {
        "repo_id": "fixture", "base_revision": tree_digest(files), "requirements": ["Inspect skills"],
        "capabilities": CAPABILITIES if capabilities is None else capabilities,
    })
    store.set_graph("broker-tenant", task["task_id"], 1, [{"node_id": "node"}])
    owner = store.claim("broker-tenant", task["task_id"], "node", "claim", 100, 3600)["owner"]
    source_root = tmp_path / "source" / "verified-repair-guide"
    shutil.copytree(ROOT / "workloads/skills/verified-repair-guide", source_root)
    if body is not None:
        raw = (source_root / "SKILL.md").read_bytes()
        closing = raw.index(b"\n---\n", 4) + 5
        (source_root / "SKILL.md").write_bytes(raw[:closing] + body)
    config = default_skills_config({"origin_id": "broker-test", "scope": "fixture", "root_label": "fixture"},
                                   "source-v1", "catalog-v1")
    capture = capture_skill_catalog([source_root], artifacts, owner["tenant_id"], owner["task_id"], config)
    package = read_catalog_snapshot(artifacts, owner["tenant_id"], owner["task_id"], capture, config)["packages"][0]
    materialize(tmp_path / "workspace", files)
    return SimpleNamespace(store=store, artifacts=artifacts, owner=owner, task=task,
                           capture=capture, config=config, package=package, source_root=source_root,
                           workspace=Workspace(tmp_path / "workspace", list(files)), previous=None)


def load(c, identity="load-0", *, package=None, catalog=None):
    return ToolCall(identity, "load_skill", {"catalog_digest": catalog or c.capture["catalog_digest"],
                    "package_digest": package or c.package["package_digest"]})


def resource(c, identity="resource-0", *, package=None):
    return ToolCall(identity, "read_skill_resource", {
        "catalog_digest": c.capture["catalog_digest"], "package_digest": package or c.package["package_digest"],
        "path": "references/checklist.md", "offset": 0, "limit": 2})


def snapshot(c):
    return c.store.snapshot(c.owner["tenant_id"], c.owner["task_id"])


def state(c):
    from service.skill_runtime import derive_loaded_skills
    return derive_loaded_skills(c.store, c.artifacts, c.owner, c.capture, c.config)


def broker(c, *, capabilities=None, configured=True):
    kwargs = {"skills_capture": c.capture, "skills_config": c.config} if configured else {}
    return ToolBroker(c.store, c.artifacts, c.owner, c.workspace,
                      CAPABILITIES if capabilities is None else capabilities, **kwargs)


def source(c, calls, *, raw_mutation=None, effect="succeeded", accepted=True, identity=None, history=None):
    """Actual v1 acceptance and ordinary model receipt; no skills advertisement."""
    owner, contract = c.owner, c.task["contract"]
    tenant, task = owner["tenant_id"], owner["task_id"]
    config = default_context_config()
    messages, evidence = history or [{"role": "user", "content": "fixture request"}], []
    system = "Follow only the frozen task constraints: " + str(contract["requirements"])
    adapter = {"provider": "scripted", "protocol": "anthropic", "adapter_version": "context_v1",
               "model": contract["model"], "endpoint": None, "system_digest": sha(canonical(system)),
               "tools_digest": sha(canonical(tool_schemas())),
               "continuation_capability": context_capability(ScriptedModel([]))}
    binding = {"tenant_id": tenant, "task_id": task, "generation": owner["generation"], "owner": owner,
               "contract_digest": sha(canonical(contract)), "source_history_digest": sha(canonical(messages)),
               "source_evidence_digest": sha(canonical(evidence)),
               "source_workspace_digest": sha(canonical(c.workspace.snapshot())),
               "source_frontier": snapshot(c)["frontier"], "expected_previous_projection_id": c.previous,
               "adapter": adapter, "config_digest": sha(canonical(config))}
    planned = plan_context(contract, messages, evidence, binding=binding, config=config, protocol="anthropic")
    request = {key: value for key, value in planned.items() if key != "offloads"}
    request_ref = c.artifacts.put_json(tenant, task, request)
    manifest = {"context_schema": 1, "strategy": config["strategy"],
                "projection_ref": c.artifacts.put_json(tenant, task, planned["projection"]),
                "projection_digest": planned["digest"],
                "raw_history_ref": c.artifacts.put_json(tenant, task, {
                    "schema": 1, "messages": messages, "evidence": evidence,
                    "workspace_digest": binding["source_workspace_digest"]}),
                **{key: binding[key] for key in ("source_history_digest", "source_evidence_digest", "source_workspace_digest")},
                "request_ref": request_ref, "request_digest": sha(canonical(request)), "binding": binding,
                "config": config, "offload_refs": [], "restored_from_projection_id": None, "source_checkpoint": None}
    identity = identity or "model-source-" + str(len(snapshot(c)["dispatches"]))
    if accepted:
        dispatch = c.store.begin_projected_dispatch(owner, identity, identity, "model.scripted",
            manifest["request_digest"], 0, projection_manifest=manifest,
            expected_frontier=binding["source_frontier"], expected_previous_projection_id=c.previous)
        c.previous = dispatch["context_acceptance"]["projection_id"]
    else:
        dispatch = c.store.begin_dispatch(owner, identity, identity, "model.scripted", manifest["request_digest"], 0)
    raw = {"type": "message", "role": "assistant", "model": "scripted-fixture-v1",
           "content": [{"type": "tool_use", "id": call.call_id, "name": call.name, "input": deepcopy(call.arguments)}
                       for call in calls], "stop_reason": "tool_use" if calls else "end_turn",
           "usage": {"input_tokens": 0, "output_tokens": 0}}
    if raw_mutation:
        raw_mutation(raw)
    ref = c.artifacts.put_json(tenant, task, raw)
    c.store.finish_dispatch(tenant, identity, "receipt-" + identity, effect, 0, ref)
    return next(d for d in snapshot(c)["dispatches"] if d["dispatch_id"] == identity)


def prepared(tmp_path, **kwargs):
    c = case(tmp_path, **kwargs)
    call = load(c)
    c.source = source(c, [call])
    c.broker = broker(c)
    c.broker.pin_context(c.source)
    c.call = call
    return c


def skill_dispatch(c, identity="load-0"):
    key = sha(canonical({"attempt": c.owner["attempt_id"], "call": identity}))[:32]
    return next(d for d in snapshot(c)["dispatches"] if d["dispatch_id"] == "dispatch-" + key)


def expected_provenance(c, call, src=None):
    src = src or c.source
    return {"schema": 1, "operation": "load" if call.name == "load_skill" else "read_resource",
            "catalog_digest": call.arguments["catalog_digest"], "package_digest": call.arguments["package_digest"],
            "path": None if call.name == "load_skill" else call.arguments["path"],
            "source_model_dispatch_id": src["dispatch_id"],
            "source_projection_id": src["context_acceptance"]["projection_id"],
            "source_accepted_sequence": src["context_acceptance"]["accepted_sequence"]}


def expected_loaded(c, call=None):
    call = call or c.call
    return {"call_id": call.call_id, "tool": "load_skill", "ok": True,
            "value": {"schema": 1, "status": "loaded", "catalog_digest": c.capture["catalog_digest"],
                      "package_digest": c.package["package_digest"], "body": c.package["body"].decode(),
                      "body_digest": sha(c.package["body"]), "source_model_dispatch_id": c.source["dispatch_id"],
                      "resources": [{"path": entry["path"], "digest": entry["artifact_ref"]["digest"],
                                     "size": entry["artifact_ref"]["size"]}
                                    for entry in c.package["manifest"]["resources"]]},
            "skill_provenance": expected_provenance(c, call)}


def test_load_is_exact_ordinary_receipt_and_origin_independent(tmp_path):
    c = prepared(tmp_path)
    before = snapshot(c)
    (c.source_root / "SKILL.md").write_text("changed source")
    (c.source_root / "references/checklist.md").write_text("changed resource")
    assert state(c)["loaded"] == []
    result = c.broker.execute(c.call)
    assert result == expected_loaded(c)
    dispatch = skill_dispatch(c)
    assert set(dispatch["parameters"]) == {"owner", "action_id", "dispatch_id", "kind", "input_digest", "bound_units"}
    assert dispatch["input_digest"] == sha(canonical({"call_digest": c.call.digest, "skill_call": expected_provenance(c, c.call)}))
    assert dispatch["effect_state"] == "succeeded" and dispatch["actual_units"] == 0
    assert dispatch["billing_state"] == "settled" and dispatch["bound_units"] == 0
    derived = state(c)
    assert set(derived) == {"schema", "kind", "catalog_ref", "catalog_digest", "config_ref", "config_digest", "loaded", "source_checkpoint"}
    assert derived["kind"] == "broker_skill_loads_v1" and derived["source_checkpoint"] is None
    assert derived["loaded"] == [{"package_digest": c.package["package_digest"],
                                  "load_dispatch_id": dispatch["dispatch_id"], "result_ref": dispatch["result_ref"]}]
    derived["loaded"].clear()
    assert len(state(c)["loaded"]) == 1
    assert snapshot(c)["task"]["contract"] == before["task"]["contract"]
    assert snapshot(c)["budget"] == before["budget"]


@pytest.mark.parametrize("stage", ["publish_before", "publish_after", "receipt_before", "receipt_after"])
def test_failure_windows_preserve_orphan_vs_commit(tmp_path, monkeypatch, stage):
    c = prepared(tmp_path)
    original_put, original_finish = c.artifacts.put_json, c.store.finish_dispatch
    published = []

    def publish(tenant, task, value):
        if value.get("tool") == "load_skill":
            if stage == "publish_before":
                raise RuntimeError("injected before publication")
            ref = original_put(tenant, task, value)
            published.append(ref)
            if stage == "publish_after":
                raise RuntimeError("injected after publication")
            return ref
        return original_put(tenant, task, value)

    def finish(tenant, identity, *args, **kwargs):
        if identity.startswith("dispatch-"):
            if stage == "receipt_before":
                raise RuntimeError("injected before receipt")
            saved = original_finish(tenant, identity, *args, **kwargs)
            if stage == "receipt_after":
                raise RuntimeError("injected lost ACK")
            return saved
        return original_finish(tenant, identity, *args, **kwargs)

    monkeypatch.setattr(c.artifacts, "put_json", publish)
    monkeypatch.setattr(c.store, "finish_dispatch", finish)
    with pytest.raises(RuntimeError, match="injected"):
        c.broker.execute(c.call)
    dispatch = skill_dispatch(c)
    if stage == "receipt_after":
        assert dispatch["effect_state"] == "succeeded" and len(state(c)["loaded"]) == 1
        before = snapshot(c)
        monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("duplicate republished"))
        assert c.broker.execute(c.call) == expected_loaded(c)
        assert snapshot(c) == before
    else:
        assert dispatch["effect_state"] == "in_flight" and dispatch["result_ref"] is None
        assert state(c)["loaded"] == []
        before = snapshot(c)
        with pytest.raises(RuntimeError, match="unresolved|duplicate|reconciliation"):
            c.broker.execute(c.call)
        assert snapshot(c) == before
        if stage != "publish_before":
            assert c.artifacts.get_json(c.owner["tenant_id"], c.owner["task_id"], published[0]["digest"]) == expected_loaded(c)


def test_intent_transaction_failure_leaves_no_result_or_state(tmp_path, monkeypatch):
    c = prepared(tmp_path)
    before = snapshot(c)
    original = c.store._event
    def crash(connection, guard, tenant, task, kind, payload):
        if kind == "dispatch.intent" and payload["kind"] == "load_skill":
            raise RuntimeError("intent rollback")
        return original(connection, guard, tenant, task, kind, payload)
    monkeypatch.setattr(c.store, "_event", crash)
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("result before intent"))
    with pytest.raises(RuntimeError, match="rollback"):
        c.broker.execute(c.call)
    assert snapshot(c) == before and state(c)["loaded"] == []


def test_duplicate_new_pin_and_new_action_use_direct_original_root(tmp_path, monkeypatch):
    c = prepared(tmp_path)
    first = c.broker.execute(c.call)
    original = skill_dispatch(c)
    next_call = load(c, "load-1")
    newer = source(c, [next_call])
    c.broker.pin_context(newer)
    before = snapshot(c)
    original_put = c.artifacts.put_json
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("known duplicate republished"))
    assert c.broker.execute(c.call) == first
    assert snapshot(c) == before
    monkeypatch.setattr(c.artifacts, "put_json", original_put)
    second = c.broker.execute(next_call)
    assert second == {"call_id": next_call.call_id, "tool": "load_skill", "ok": True,
                      "value": {"schema": 1, "status": "already_loaded", "catalog_digest": c.capture["catalog_digest"],
                                "package_digest": c.package["package_digest"], "load_dispatch_id": original["dispatch_id"]},
                      "skill_provenance": expected_provenance(c, next_call, newer)}
    assert state(c)["loaded"][0]["load_dispatch_id"] == original["dispatch_id"]
    changed = load(c, "load-0", package="f" * 64)
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.broker.execute(changed)
    assert snapshot(c) == before


@pytest.mark.parametrize("same_response", [True, False])
def test_resource_remains_failed_known_without_accepted_disclosure(tmp_path, same_response):
    c = case(tmp_path)
    primary, read = load(c), resource(c)
    c.source = source(c, [primary, read] if same_response else [primary])
    c.call, c.broker = primary, broker(c)
    c.broker.pin_context(c.source)
    c.broker.execute(primary)
    if not same_response:
        c.source = source(c, [read])
        c.broker.pin_context(c.source)
    result = c.broker.execute(read)
    assert result == {"call_id": read.call_id, "tool": read.name, "ok": False,
                      "error_type": "SkillError", "message": "not_disclosed",
                      "skill_provenance": expected_provenance(c, read)}
    assert "data" not in canonical(result).decode()
    before = snapshot(c)
    assert c.broker.execute(read) == result
    assert snapshot(c) == before and len(state(c)["loaded"]) == 1


@pytest.mark.parametrize("tool,code", [("load_skill", "invalid_package"), ("read_skill_resource", "resource_denied")])
def test_wrong_package_is_exact_reusable_failed_known(tmp_path, tool, code):
    c = case(tmp_path)
    call = load(c, package="f" * 64) if tool == "load_skill" else resource(c, package="f" * 64)
    c.source = source(c, [call])
    b = broker(c)
    b.pin_context(c.source)
    expected = {"call_id": call.call_id, "tool": tool, "ok": False, "error_type": "SkillError",
                "message": code, "skill_provenance": expected_provenance(c, call)}
    assert b.execute(call) == expected
    before = snapshot(c)
    assert b.execute(call) == expected and snapshot(c) == before
    assert state(c)["loaded"] == []


@pytest.mark.parametrize("fault", ["unconfigured", "broker_load", "broker_read", "contract_load", "contract_read", "unproposed", "model", "failed", "unknown", "unaccepted", "catalog", "mutated_arguments"])
def test_authority_source_and_call_rejection_has_no_new_intent(tmp_path, fault):
    durable = [x for x in CAPABILITIES if x != {"contract_load": "load_skill", "contract_read": "read_skill_resource"}.get(fault)]
    c = case(tmp_path, capabilities=durable)
    call = load(c, catalog="f" * 64) if fault == "catalog" else load(c)
    c.source = source(c, [] if fault == "unproposed" else [call],
        raw_mutation=(lambda raw: raw.update(model="forged")) if fault == "model" else None,
        effect={"failed": "failed_known", "unknown": "unknown"}.get(fault, "succeeded"),
        accepted=fault != "unaccepted")
    constructor_caps = [x for x in CAPABILITIES if x != {"broker_load": "load_skill", "broker_read": "read_skill_resource"}.get(fault)]
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        b = broker(c, capabilities=constructor_caps, configured=fault != "unconfigured")
        b.pin_context(c.source)
        if fault == "mutated_arguments":
            call.arguments["extra"] = "after frozen dataclass construction"
        b.execute(call)
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["stale", "cancel", "expired", "scope"])
def test_new_action_requires_current_source_owner_and_scope(tmp_path, fault):
    c = prepared(tmp_path)
    if fault == "stale":
        source(c, [load(c, "newer")])
    elif fault == "cancel":
        c.store.cancel(c.owner["tenant_id"], c.owner["task_id"], "cancel")
    elif fault == "expired":
        with c.store._tx() as (connection, _guard):
            row = c.store._get(connection, "attempts", c.owner["attempt_id"], c.owner["tenant_id"], c.owner["task_id"])
            row["lease_until"] = 0
            c.store._save(connection, "attempts", c.owner["attempt_id"], c.owner["tenant_id"], c.owner["task_id"], row)
    else:
        c.broker.owner = {**c.owner, "task_id": "foreign-task"}
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.broker.execute(c.call)
    assert snapshot(c) == before


def test_disabled_schemas_keep_frozen_bytes_and_strict_new_arguments():
    # Pinned from the before-code legacy-tool-schemas.json freeze, independent of new renderers.
    assert sha(canonical(tool_schemas())) == "94a98fb1e4b42bf5864bdcd789a74ea65b0fba9d9d77fca4b1111614ef1bb0d9"
    assert sha(canonical(tool_schemas(include_context=True))) == "b133fd6abcc0d66abe3be2e0a61427296b65003d6f5614e79d1d805ae0b38c4f"
    assert {x["name"] for x in tool_schemas(include_skills=True)} == {"read_file", "search", "replace_text", "run_tests", "finish", "load_skill", "read_skill_resource"}
    for field in ("offset", "limit"):
        args = {"catalog_digest": "a" * 64, "package_digest": "b" * 64, "path": "references/a.txt", "offset": 0, "limit": 1}
        args[field] = True
        with pytest.raises(ProtocolError):
            ToolCall("read", "read_skill_resource", args)
    for bad in (1, None, "yes"):
        with pytest.raises(ValueError):
            tool_schemas(include_skills=bad)


def mutate_row(c, table, key, mutate):
    with c.store._tx() as (connection, _guard):
        row = c.store._get(connection, table, key, c.owner["tenant_id"], c.owner["task_id"])
        mutate(row)
        c.store._save(connection, table, key, c.owner["tenant_id"], c.owner["task_id"], row)


def replace_result(c, dispatch, value):
    ref = c.artifacts.put_json(c.owner["tenant_id"], c.owner["task_id"], value)
    mutate_row(c, "dispatches", dispatch["dispatch_id"], lambda row: row.update(result_ref=ref))
    mutate_row(c, "receipts", digest_json([c.owner["tenant_id"], dispatch["receipt_id"]]), lambda row: row.update(result_ref=ref))


@pytest.mark.parametrize("fault", ["body", "resources", "call_id", "source", "provenance", "result_missing", "receipt_missing", "receipt_effect", "receipt_result", "charge", "catalog", "input_digest", "nonobject_list", "nonobject_string", "nonobject_int", "nonobject_bool", "nonobject_null"])
def test_coherent_result_and_record_forgery_cannot_become_loaded(tmp_path, fault):
    c = prepared(tmp_path)
    result = c.broker.execute(c.call)
    dispatch = skill_dispatch(c)
    if fault.startswith("nonobject_"):
        forged = {"nonobject_list": [], "nonobject_string": "label", "nonobject_int": 1,
                  "nonobject_bool": True, "nonobject_null": None}[fault]
        replace_result(c, dispatch, forged)
    elif fault in {"body", "resources", "call_id", "source", "provenance"}:
        forged = deepcopy(result)
        if fault == "body":
            forged["value"]["body"] += "forged"
            forged["value"]["body_digest"] = sha(forged["value"]["body"].encode())
        elif fault == "resources":
            forged["value"]["resources"][0]["digest"] = "f" * 64
        elif fault == "call_id":
            forged["call_id"] = "other-call"
        elif fault == "source":
            forged["value"]["source_model_dispatch_id"] = "foreign-source"
        else:
            forged["skill_provenance"]["source_accepted_sequence"] += 1
        replace_result(c, dispatch, forged)
    elif fault == "result_missing":
        mutate_row(c, "dispatches", dispatch["dispatch_id"], lambda row: row.update(result_ref=None))
    elif fault == "receipt_missing":
        mutate_row(c, "dispatches", dispatch["dispatch_id"], lambda row: row.update(receipt_id="missing"))
    elif fault.startswith("receipt_"):
        key = digest_json([c.owner["tenant_id"], dispatch["receipt_id"]])
        mutate_row(c, "receipts", key, lambda row: row.update(**({"effect_state": "unknown"} if fault == "receipt_effect" else {"result_ref": c.source["result_ref"]})))
    elif fault == "charge":
        mutate_row(c, "dispatches", dispatch["dispatch_id"], lambda row: row.update(actual_units=1))
    elif fault == "catalog":
        mutate_row(c, "dispatches", dispatch["dispatch_id"], lambda row: row["skill_call"].update(catalog_digest="f" * 64))
    else:
        def change(row):
            row["input_digest"] = "f" * 64
            row["parameters"]["input_digest"] = "f" * 64
        mutate_row(c, "dispatches", dispatch["dispatch_id"], change)
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        state(c)
    with pytest.raises(REJECTIONS):
        c.broker.execute(c.call)
    assert snapshot(c) == before


def test_failed_known_error_code_forgery_is_not_reusable(tmp_path):
    c = case(tmp_path)
    read = resource(c)
    c.source = source(c, [read])
    b = broker(c)
    b.pin_context(c.source)
    result = b.execute(read)
    result["message"] = "unsupported_profile"
    replace_result(c, skill_dispatch(c, read.call_id), result)
    with pytest.raises(REJECTIONS):
        state(c)
    with pytest.raises(REJECTIONS):
        b.execute(read)


def test_already_loaded_cycle_never_replaces_primary_membership(tmp_path):
    c = prepared(tmp_path)
    c.broker.execute(c.call)
    second = load(c, "load-1")
    new_source = source(c, [second])
    c.broker.pin_context(new_source)
    result = c.broker.execute(second)
    dispatch = skill_dispatch(c, second.call_id)
    result["value"]["load_dispatch_id"] = dispatch["dispatch_id"]
    replace_result(c, dispatch, result)
    with pytest.raises(REJECTIONS):
        state(c)


def generic(c, count):
    for index in range(count):
        identity = "generic-" + str(index)
        c.store.begin_dispatch(c.owner, identity, identity, "finish", "a" * 64, 0)
        c.store.finish_dispatch(c.owner["tenant_id"], identity, "receipt-" + identity, "succeeded", 0)


def test_64_record_cap_is_exact_without_truncating_loaded_state(tmp_path):
    c = prepared(tmp_path)
    generic(c, 30)  # Model dispatch+receipt and 30 pairs = 62 records.
    assert len(c.store.read_skill_records(c.owner)["dispatches"]) == 31
    c.broker.execute(c.call)  # The intent and its terminal receipt consume exactly two slots.
    records = c.store.read_skill_records(c.owner)
    assert len(records["dispatches"]) + len(records["receipts"]) == 64
    assert len(state(c)["loaded"]) == 1
    before = snapshot(c)
    metadata = expected_provenance(c, c.call)
    with pytest.raises(REJECTIONS):
        c.store.begin_skill_dispatch(c.owner, "beyond", "beyond", c.call.digest, metadata, before["frontier"])
    assert snapshot(c) == before
    c.store.begin_dispatch(c.owner, "ordinary-65", "ordinary-65", "finish", "b" * 64, 0)
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.store.read_skill_records(c.owner)
    with pytest.raises(REJECTIONS):
        state(c)
    assert snapshot(c) == before


def test_stale_preparation_frontier_refuses_parallel_primary(tmp_path):
    c = prepared(tmp_path)
    frontier = snapshot(c)["frontier"]
    metadata = expected_provenance(c, c.call)
    identity = sha(canonical({"attempt": c.owner["attempt_id"], "call": c.call.call_id}))[:32]
    first = c.store.begin_skill_dispatch(c.owner, "action-" + identity, "dispatch-" + identity,
                                         c.call.digest, metadata, frontier)
    assert first["effect_state"] == "in_flight"
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.store.begin_skill_dispatch(c.owner, "parallel", "parallel", c.call.digest, metadata, frontier)
    assert snapshot(c) == before and state(c)["loaded"] == []


@pytest.mark.parametrize("committed", [False, True])
def test_interleaved_duplicate_at_intent_never_republishes_or_reexecutes(tmp_path, monkeypatch, committed):
    c = prepared(tmp_path)
    original_begin = c.store.begin_skill_dispatch
    original_put = c.artifacts.put_json
    original_finish = c.store.finish_dispatch
    after_race, publications, receipts = [], [], []

    def interleave(owner, action_id, dispatch_id, call_digest, metadata, frontier):
        inserted = original_begin(owner, action_id, dispatch_id, call_digest, metadata, frontier)
        assert not inserted["duplicate"]
        if committed:
            ref = original_put(owner["tenant_id"], owner["task_id"], expected_loaded(c))
            identity = dispatch_id.removeprefix("dispatch-")
            original_finish(owner["tenant_id"], dispatch_id, "receipt-" + identity, "succeeded", 0, ref)
        after_race.append(snapshot(c))
        return original_begin(owner, action_id, dispatch_id, call_digest, metadata, frontier)

    def publication(*args, **kwargs):
        publications.append(args)
        return original_put(*args, **kwargs)

    def receipt(*args, **kwargs):
        receipts.append(args)
        return original_finish(*args, **kwargs)

    monkeypatch.setattr(c.store, "begin_skill_dispatch", interleave)
    monkeypatch.setattr(c.artifacts, "put_json", publication)
    monkeypatch.setattr(c.store, "finish_dispatch", receipt)
    if committed:
        assert c.broker.execute(c.call) == expected_loaded(c)
    else:
        with pytest.raises(REJECTIONS):
            c.broker.execute(c.call)
    assert len(after_race) == 1 and snapshot(c) == after_race[0]
    assert publications == receipts == []


def test_read_records_detached_and_direct_provenance_duplicate_conflict(tmp_path):
    c = prepared(tmp_path)
    c.broker.execute(c.call)
    records = c.store.read_skill_records(c.owner)
    assert set(records) == {"owner", "contract", "frontier", "dispatches", "receipts"}
    assert len(records["dispatches"]) == len(records["receipts"]) == 2
    records["dispatches"].clear()
    records["contract"]["capabilities"].clear()
    assert len(c.store.read_skill_records(c.owner)["dispatches"]) == 2
    dispatch = skill_dispatch(c)
    changed = deepcopy(dispatch["skill_call"])
    changed["source_accepted_sequence"] += 1
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.store.begin_skill_dispatch(c.owner, dispatch["action_id"], dispatch["dispatch_id"], c.call.digest, changed, before["frontier"])
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["schema_bool", "sequence_bool", "load_path", "extra", "operation", "uppercase_digest", "resource_path"])
def test_closed_provenance_metadata_is_checked_before_intent(tmp_path, fault):
    c = prepared(tmp_path)
    metadata = expected_provenance(c, c.call)
    if fault == "schema_bool":
        metadata["schema"] = True
    elif fault == "sequence_bool":
        metadata["source_accepted_sequence"] = True
    elif fault == "load_path":
        metadata["path"] = "references/checklist.md"
    elif fault == "extra":
        metadata["extra"] = "caller state"
    elif fault == "operation":
        metadata["operation"] = "execute"
    elif fault == "uppercase_digest":
        metadata["package_digest"] = "A" * 64
    else:
        metadata.update(operation="read_resource", path="../private")
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.store.begin_skill_dispatch(c.owner, "bad", "bad", c.call.digest, metadata, before["frontier"])
    assert snapshot(c) == before


def test_receipt_derivation_survives_unrelated_uncertainty_but_not_new_work(tmp_path):
    c = prepared(tmp_path)
    c.broker.execute(c.call)
    loaded = state(c)["loaded"]
    c.store.begin_dispatch(c.owner, "uncertain", "uncertain", "finish", "c" * 64, 0)
    assert state(c)["loaded"] == loaded
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.store.begin_skill_dispatch(c.owner, "new", "new", c.call.digest,
                                     expected_provenance(c, c.call), before["frontier"])
    assert snapshot(c) == before


@pytest.mark.parametrize("effect", ["unknown", "not_dispatched"])
def test_zero_settled_uncertain_or_not_dispatched_receipt_is_not_a_load(tmp_path, effect):
    c = prepared(tmp_path)
    identity = sha(canonical({"attempt": c.owner["attempt_id"], "call": c.call.call_id}))[:32]
    c.store.begin_skill_dispatch(c.owner, "action-" + identity, "dispatch-" + identity, c.call.digest,
                                 expected_provenance(c, c.call), snapshot(c)["frontier"])
    c.store.finish_dispatch(c.owner["tenant_id"], "dispatch-" + identity, "receipt-" + identity, effect, 0)
    assert state(c)["loaded"] == []
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.broker.execute(c.call)
    assert snapshot(c) == before


def test_heartbeat_between_preflight_and_begin_fences_without_publishing(tmp_path, monkeypatch):
    c = prepared(tmp_path)
    original = c.store.begin_skill_dispatch
    after_heartbeat = []
    def heartbeat_then_begin(*args):
        c.store.heartbeat(c.owner, 3600)
        after_heartbeat.append(snapshot(c))
        return original(*args)
    monkeypatch.setattr(c.store, "begin_skill_dispatch", heartbeat_then_begin)
    monkeypatch.setattr(c.artifacts, "put_json", lambda *a, **k: pytest.fail("stale frontier published result"))
    with pytest.raises(REJECTIONS):
        c.broker.execute(c.call)
    assert snapshot(c) == after_heartbeat[0] and state(c)["loaded"] == []


def test_call_id_reused_from_source_history_cannot_authorize_new_load(tmp_path):
    c = case(tmp_path)
    call = load(c)
    history = [{"role": "user", "content": "fixture request"},
               {"role": "assistant", "content": [{"type": "tool_use", "id": call.call_id,
                   "name": "finish", "input": {"summary": "old"}}]},
               {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call.call_id, "content": "old result"}]}]
    c.source = source(c, [call], history=history)
    b = broker(c)
    b.pin_context(c.source)
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        b.execute(call)
    assert snapshot(c) == before


def test_two_coherently_hashed_primary_roots_are_rejected(tmp_path):
    c = prepared(tmp_path)
    c.broker.execute(c.call)
    second = load(c, "load-1")
    c.source = source(c, [second])
    c.broker.pin_context(c.source)
    c.broker.execute(second)
    replace_result(c, skill_dispatch(c, second.call_id), expected_loaded(c, second))
    with pytest.raises(REJECTIONS):
        state(c)


def test_broker_selection_is_deep_frozen_and_foreign_capture_is_rejected(tmp_path):
    c = prepared(tmp_path)
    capture, config = deepcopy(c.capture), deepcopy(c.config)
    c.capture["catalog_digest"] = "f" * 64
    c.config["origin"]["origin_id"] = "altered caller object"
    result = c.broker.execute(c.call)
    assert result["value"]["catalog_digest"] == capture["catalog_digest"]
    c.capture, c.config = capture, config
    assert len(state(c)["loaded"]) == 1
    foreign = deepcopy(c.capture)
    foreign["catalog_ref"]["tenant_id"] = "foreign-tenant"
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        ToolBroker(c.store, c.artifacts, c.owner, c.workspace, CAPABILITIES,
                   skills_capture=foreign, skills_config=c.config)
    assert snapshot(c) == before


def test_exact_full_wrapper_cap_is_accepted_without_truncation(tmp_path):
    empty = prepared(tmp_path / "empty", body=b"")
    base = len(canonical(expected_loaded(empty)))
    remaining = 65536 - base
    body = b"\\" * (remaining // 2) + b"x" * (remaining % 2)
    c = prepared(tmp_path / "boundary", body=body)
    expected = expected_loaded(c)
    assert len(canonical(expected)) == 65536 and len(body) <= 32768
    assert c.broker.execute(c.call) == expected
    assert len(state(c)["loaded"]) == 1


def test_escaped_full_wrapper_is_bounded_before_intent(tmp_path):
    c = prepared(tmp_path, body=b"\\" * 32768)
    assert len(c.package["body"]) == 32768 and len(canonical(expected_loaded(c))) > 65536
    before = snapshot(c)
    with pytest.raises(REJECTIONS):
        c.broker.execute(c.call)
    assert snapshot(c) == before and state(c)["loaded"] == []


def test_missing_snapshot_has_sanitized_error_and_no_fallback(tmp_path):
    c = prepared(tmp_path)
    ref = c.package["manifest"]["body_ref"]
    c.artifacts._path(c.owner["tenant_id"], c.owner["task_id"], ref["digest"]).unlink()
    before = snapshot(c)
    with pytest.raises(SkillError) as error:
        c.broker.execute(c.call)
    rendered = "".join(traceback.format_exception(error.value))
    assert str(tmp_path) not in rendered and "Traceback" not in error.value.args[0]
    assert snapshot(c) == before
