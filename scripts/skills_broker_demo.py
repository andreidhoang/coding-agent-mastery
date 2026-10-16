"""Offline broker receipt trace; no provider send, workspace tool, or skill execution.

Run: .venv/bin/python -m scripts.skills_broker_demo --output /fresh/directory
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from service.artifacts import LocalArtifacts, canonical_bytes, digest_bytes, digest_json
from service.context import default_context_config, plan_context
from service.harness import ToolBroker
from service.protocol import ToolCall, tool_schemas
from service.providers import ScriptedModel, context_capability
from service.skills import capture_skill_catalog, default_skills_config
from service.storage import RuntimeStore
import workloads


def write(path, value):
    path.write_bytes(canonical_bytes(value) + b"\n")


def setup(path):
    path.mkdir(parents=True)
    artifacts = LocalArtifacts(path / "artifacts")
    store = RuntimeStore("sqlite:///" + str(path / "runtime.db"), artifacts)
    task = store.submit("broker-demo", "receipt-trace", {
        "repo_id": "authored-skills-fixture", "base_revision": "a" * 64,
        "requirements": ["Demonstrate broker loading using durable scripted evidence."],
        "model": "scripted-fixture-v1", "capabilities": ["load_skill", "read_skill_resource"],
    })
    tenant, task_id = task["tenant_id"], task["task_id"]
    store.set_graph(tenant, task_id, 1, [{"node_id": "node"}])
    grant = store.claim(tenant, task_id, "node", "claim", 0, 120)
    owner = grant["owner"]
    config = default_skills_config({"origin_id": "authored-fixture", "scope": "fixture",
                                    "root_label": "verified-repair-guide"}, "authored-v1", "broker-demo-v1")
    capture = capture_skill_catalog([Path(workloads.__file__).parent / "skills/verified-repair-guide"],
                                   artifacts, tenant, task_id, config)
    catalog = artifacts.get_json(tenant, task_id, capture["catalog_ref"]["digest"])
    package = catalog["entries"][0]["package_digest"]
    args = {"catalog_digest": capture["catalog_digest"], "package_digest": package}
    calls = [ToolCall("primary", "load_skill", args), ToolCall("new-call", "load_skill", dict(args)),
             ToolCall("resource", "read_skill_resource", {**args, "path": "references/checklist.md",
                                                          "offset": 0, "limit": 2})]
    # This manually persisted scripted response tests the broker seam. It is not
    # a skills-aware Harness request or evidence that a catalog was disclosed.
    contract = task["contract"]
    context_config = default_context_config()
    messages = [{"role": "user", "content": "\n".join(contract["requirements"])}]
    system = "Follow only the frozen task constraints: " + str(contract["requirements"])
    frontier = store.snapshot(tenant, task_id)["frontier"]
    binding = {
        "tenant_id": tenant, "task_id": task_id, "generation": owner["generation"], "owner": owner,
        "contract_digest": digest_json(contract), "source_history_digest": digest_json(messages),
        "source_evidence_digest": digest_json([]), "source_workspace_digest": digest_json({}),
        "source_frontier": frontier, "expected_previous_projection_id": None,
        "config_digest": digest_json(context_config),
        "adapter": {"provider": "scripted", "protocol": "anthropic", "adapter_version": "context_v1",
                    "model": contract["model"], "endpoint": None, "system_digest": digest_json(system),
                    "tools_digest": digest_json(tool_schemas()),
                    "continuation_capability": context_capability(ScriptedModel([]))},
    }
    plan = plan_context(contract, messages, [], binding=binding, config=context_config, protocol="anthropic")
    request = {k: v for k, v in plan.items() if k != "offloads"}
    manifest = {
        "context_schema": 1, "strategy": context_config["strategy"],
        "projection_ref": artifacts.put_json(tenant, task_id, plan["projection"]),
        "projection_digest": plan["digest"],
        "raw_history_ref": artifacts.put_json(tenant, task_id, {
            "schema": 1, "messages": messages, "evidence": [], "workspace_digest": digest_json({})}),
        **{k: binding[k] for k in ("source_history_digest", "source_evidence_digest", "source_workspace_digest")},
        "request_ref": artifacts.put_json(tenant, task_id, request), "request_digest": digest_json(request),
        "binding": binding, "config": context_config, "offload_refs": [],
        "source_checkpoint": None, "restored_from_projection_id": None,
    }
    source = store.begin_projected_dispatch(owner, "source", "source", "model.scripted", digest_json(request), 0,
                                            projection_manifest=manifest, expected_frontier=frontier,
                                            expected_previous_projection_id=None)
    response = ScriptedModel([calls]).response(0)
    response_ref = artifacts.put_json(tenant, task_id, response.raw)
    store.finish_dispatch(tenant, source["dispatch_id"], "source-receipt", "succeeded", 0, response_ref)
    broker = ToolBroker(store, artifacts, owner, None, contract["capabilities"],
                        skills_capture=capture, skills_config=config)
    broker.pin_context(source)
    return store, artifacts, grant, broker, capture, config, calls


def run_case(path, mode):
    from service.skill_runtime import derive_loaded_skills

    store, artifacts, grant, broker, capture, config, calls = setup(path)
    owner = grant["owner"]
    tenant, task = owner["tenant_id"], owner["task_id"]
    def state():
        return derive_loaded_skills(store, artifacts, owner, capture, config)
    before = state()
    assert before["loaded"] == []
    observation = {"mode": mode, "before": before}
    original_finish = store.finish_dispatch
    if mode != "normal":
        def interrupted(*args, **kwargs):
            if mode == "lost_ack":
                original_finish(*args, **kwargs)
            raise RuntimeError("injected receipt boundary interruption")
        store.finish_dispatch = interrupted
        existing = {p for p in artifacts.root.rglob("*") if p.is_file()}
        try:
            broker.execute(calls[0])
        except RuntimeError as error:
            assert str(error) == "injected receipt boundary interruption"
        else:
            raise AssertionError("injected failure was not observed")
        finally:
            store.finish_dispatch = original_finish
        observation["after_interruption"] = state()
        observation["published_artifacts"] = [str(p.relative_to(path)) for p in artifacts.root.rglob("*")
                                               if p.is_file() and p not in existing]
        assert len(observation["after_interruption"]["loaded"]) == (1 if mode == "lost_ack" else 0)
        saved = deepcopy(store.snapshot(tenant, task))
        if mode == "orphan":
            try:
                broker.execute(calls[0])
            except RuntimeError:
                observation["unresolved_retry_refused"] = True
            else:
                raise AssertionError("unresolved load replayed")
        else:
            observation["retried_result"] = broker.execute(calls[0])
            assert observation["retried_result"]["value"]["status"] == "loaded"
        assert store.snapshot(tenant, task) == saved
        observation["retry_no_durable_changes"] = True
    else:
        first = broker.execute(calls[0])
        loaded = state()
        assert len(loaded["loaded"]) == 1
        saved = deepcopy(store.snapshot(tenant, task))
        assert broker.execute(calls[0]) == first
        assert store.snapshot(tenant, task) == saved
        second = broker.execute(calls[1])
        assert second["value"]["status"] == "already_loaded"
        assert second["value"]["load_dispatch_id"] == loaded["loaded"][0]["load_dispatch_id"]
        resource = broker.execute(calls[2])
        assert resource["ok"] is False and resource["message"] == "not_disclosed"
        assert state() == loaded
        observation.update(first=first, duplicate_exact=True, duplicate_no_durable_changes=True,
                           second=second, resource=resource)
    observation["final_state"] = state()
    # No physical process was started. Retire only this fixture's logical slot.
    store.retire_sandbox(tenant, grant["sandbox_id"], {"supervisor": "trusted-no-process-fixture",
                                                    "exit_observed": True})
    observation["final_snapshot"] = store.snapshot(tenant, task)
    write(path / "observation.json", observation)
    store.engine.dispose()
    return {"case": mode, "loaded_count": len(observation["final_state"]["loaded"]),
            "observation": str((path / "observation.json").name),
            "sha256": digest_bytes((path / "observation.json").read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    cases = [run_case(output / name, name) for name in ("normal", "orphan", "lost_ack")]
    summary = {"schema": 1, "status": "passed", "scope": "offline_scripted_broker_seam",
               "paid_execution": False, "provider_sends": 0, "accepted_catalog_disclosure": False,
               "checkpoint_recovery": False, "human_mastery": "not_assessed", "cases": cases}
    write(output / "summary.json", summary)
    (output / "trace.md").write_text("""# Broker load: observed receipt boundary

- Normal: empty → committed primary load → exact retry (no events/cost) → new call returns direct already_loaded → resource denied not_disclosed.
- Orphan: intent → result artifact → receipt write interruption → loaded remains empty; explicit retry refuses unresolved dispatch.
- Lost ACK: intent → result → committed receipt → caller interruption → loaded contains one primary; explicit retry returns original result without durable changes.

Each case uses real local SQLite dispatch/receipt transactions and a manually persisted scripted model response. No model request is sent. Context-v1 binds the response source but does not prove catalog disclosure. No skills-aware Harness/checkpoint or restored-owner path is claimed.

**VI:** Hai exception có thể nhìn giống nhau từ caller, nhưng DB khác nhau: chưa commit receipt thì vẫn unresolved; đã commit mà mất ACK thì phải đọc lại result cũ. Ba fixture chỉ chứng minh cơ chế broker, không chứng minh model đã thấy skill hoặc dùng skill tốt hơn.
""")
    print(json.dumps({"status": "passed", "output": str(output),
                      "summary_sha256": digest_bytes((output / "summary.json").read_bytes())}))


if __name__ == "__main__":
    main()
