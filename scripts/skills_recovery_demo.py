"""Three owners, two historical state cuts, and native mock HTTP reconstruction.

Run: .venv/bin/python -m scripts.skills_recovery_demo --output /fresh/directory
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
import shutil

import httpx
import workloads

from service.artifacts import LocalArtifacts, digest_bytes, digest_json
from service.context import default_context_config
from service.execution import Workspace, materialize, tree_digest
from service.harness import Harness
from service.providers import NebiusChatCompletions
from service.recovery import restore_checkpoint
from service.skills import capture_skill_catalog, default_skills_config, read_catalog_snapshot
from service.storage import RuntimeStore
from .skills_disclosure_demo import MODEL, rates, response, write


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifacts = LocalArtifacts(output / "artifacts")
    url = "sqlite:///" + str(output / "runtime.db")
    store = RuntimeStore(url, artifacts)
    files = {"README.txt": "Trusted mock fixture; no candidate process execution.\n"}
    task = store.submit("recovery-demo", "three-owner-native", {
        "repo_id": "authored-skills-fixture", "base_revision": tree_digest(files),
        "requirements": ["Load a captured skill, recover under new owners, read captured bytes, and propose completion."],
        "model": MODEL, "capabilities": ["load_skill", "read_skill_resource"], "rate_snapshot": rates()})
    tenant, task_id = task["tenant_id"], task["task_id"]
    store.set_graph(tenant, task_id, 1, [{"node_id": "node"}])
    grant = store.claim(tenant, task_id, "node", "claim-A", 100, 3600)
    materialize(output / "workspace", files)
    workspace = Workspace(output / "workspace", list(files))
    origin = output / "origin" / "verified-repair-guide"
    shutil.copytree(Path(workloads.__file__).parent / "skills/verified-repair-guide", origin)
    config = default_skills_config({"origin_id": "authored-fixture", "scope": "fixture", "root_label": "guide"},
                                   "authored-v1", "recovery-demo-v1")
    capture = capture_skill_catalog([origin], artifacts, tenant, task_id, config)
    package = read_catalog_snapshot(artifacts, tenant, task_id, capture, config)["packages"][0]
    resource_path = "references/checklist.md"
    resource = package["resources"][resource_path]
    arguments = {"catalog_digest": capture["catalog_digest"], "package_digest": package["package_digest"]}
    batches = [[("load-A", "load_skill", arguments)],
               [("resource-B", "read_skill_resource", {**arguments, "path": resource_path,
                                                       "offset": 0, "limit": 8192})], []]
    observations, checkpoints, restored, original_receipts = [], [], None, None

    for index, label in enumerate("ABC"):
        owner = grant["owner"]

        def handler(request):
            assert len(observations) == index, "unexpected model send"
            wire = bytes(request.content)
            actual = json.loads(wire)
            dispatch = next(d for d in store.read_skill_proof(owner)["dispatches"]
                            if d["dispatch_id"] == f"model-{owner['attempt_id']}-{index}")
            accepted = dispatch["context_acceptance"]
            manifest = accepted["manifest"]
            saved = artifacts.get_json(tenant, task_id, manifest["request_ref"]["digest"])
            state = artifacts.get_json(tenant, task_id, manifest["skills_state_ref"]["digest"])
            assert saved["payload"] == actual and digest_json(saved) == dispatch["input_digest"]
            assert len(state["loaded"]) == (0 if index == 0 else 1)
            if restored is not None:
                assert actual["messages"][1:] == restored["messages"]
                assert state["source_checkpoint"] == restored["source_checkpoint"]
                assert manifest["binding"]["expected_previous_projection_id"] is None
            (output / f"request-{label}.wire.json").write_bytes(wire)
            observation = {"owner_label": label, "owner": owner, "turn": index,
                           "dispatch_id": dispatch["dispatch_id"], "acceptance": accepted,
                           "skills_before_response": state, "request_record": saved,
                           "wire_sha256": digest_bytes(wire), "canonical_payload_digest": digest_json(actual)}
            observations.append(deepcopy(observation))
            write(output / f"request-{label}.observation.json", observation)
            return httpx.Response(200, json=response(batches[index], index))

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            model = NebiusChatCompletions("mock-never-live", MODEL, enable_network=True, client=client)
            harness = Harness(store, artifacts, max_turns=3, provider_envelopes={MODEL: rates()},
                              context_config=default_context_config(), skills_capture=capture, skills_config=config)
            result = harness.run(owner, task["contract"], workspace, model, restored=restored,
                                 pause_after_turn=index + 1 if index < 2 else None)
            assert result["status"] == ("paused" if index < 2 else "completion_proposed")
            before_restore = store.snapshot(tenant, task_id)
            restored = restore_checkpoint(store, artifacts, tenant, task_id, result["checkpoint_id"])
            assert store.snapshot(tenant, task_id) == before_restore
            assert len(restored["skills_state"]["loaded"]) == 1
            checkpoints.append({"owner_label": label, "checkpoint_id": result["checkpoint_id"],
                                "context": restored["context"], "skills_after_turn": restored["skills_state"]})
            write(output / f"checkpoint-{label}.json", checkpoints[-1])
            if original_receipts is None:
                original_receipts = store.read_skill_proof(owner)["receipts"]
            assert all(r in store.read_skill_proof(owner)["receipts"] for r in original_receipts)
            if index == 2:
                original_put, original_json = artifacts.put, artifacts.put_json

                def forbidden(*args, **kwargs):
                    raise AssertionError("completed restore published or sent")

                artifacts.put = artifacts.put_json = model.receive = forbidden
                try:
                    repeated = harness.run(owner, task["contract"], workspace, model, restored=restored)
                finally:
                    artifacts.put, artifacts.put_json = original_put, original_json
                assert repeated == result and store.snapshot(tenant, task_id) == before_restore
        if index == 0:
            (origin / "SKILL.md").write_text("origin changed after immutable capture")
            (origin / resource_path).write_text("origin resource changed")
        if index < 2:
            store.retire_sandbox(tenant, grant["sandbox_id"], {
                "supervisor": "trusted-no-process-fixture", "exit_observed": True})
            write(output / f"snapshot-{label}-retired.json", store.snapshot(tenant, task_id))
            store.close()
            artifacts = LocalArtifacts(output / "artifacts")
            store = RuntimeStore(url, artifacts)
            again = restore_checkpoint(store, artifacts, tenant, task_id, result["checkpoint_id"])
            assert again == restored
            grant = store.claim(tenant, task_id, "node", "claim-" + "ABC"[index + 1], 100, 3600)

    final = store.snapshot(tenant, task_id)
    root = checkpoints[0]["skills_after_turn"]["loaded"][0]
    assert all(k["skills_after_turn"]["loaded"] == [root] for k in checkpoints)
    assert [k["skills_after_turn"]["source_checkpoint"] for k in checkpoints] == [
        None, checkpoints[0]["checkpoint_id"], checkpoints[1]["checkpoint_id"]]
    read = next(d for d in final["dispatches"] if d["kind"] == "read_skill_resource")
    read_result = artifacts.get_json(tenant, task_id, read["result_ref"]["digest"])
    assert read_result["ok"] and base64.b64decode(read_result["value"]["data"], validate=True) == resource
    assert read_result["skill_provenance"]["source_model_dispatch_id"] == observations[1]["dispatch_id"]
    original_assistant = observations[1]["request_record"]["payload"]["messages"][2]
    assert original_assistant["reasoning_content"] == "opaque authored fixture field for turn 0"
    assert observations[2]["request_record"]["payload"]["messages"][2] == original_assistant
    write(output / "snapshot-before-retirement.json", final)
    store.retire_sandbox(tenant, grant["sandbox_id"], {
        "supervisor": "trusted-no-process-fixture", "exit_observed": True})
    write(output / "snapshot.json", store.snapshot(tenant, task_id))
    write(output / "capture.json", capture)
    write(output / "result.json", result)
    store.close()
    summary = {"schema": 1, "status": "passed", "scope": "three_owner_skills_recovery_native_mock_http",
               "request_count": len(observations), "checkpoint_count": len(checkpoints),
               "accepted_loaded_counts": [len(o["skills_before_response"]["loaded"]) for o in observations],
               "post_turn_loaded_counts": [len(k["skills_after_turn"]["loaded"]) for k in checkpoints],
               "original_load_dispatch_id": root["load_dispatch_id"],
               "checkpoint_ids": [k["checkpoint_id"] for k in checkpoints],
               "resource_sha256": digest_bytes(resource), "resource_bytes": len(resource),
               "clean_reopen_count": 2, "origin_mutation_ignored": True, "opaque_fields_preserved": True,
               "completed_restore_sends": 0, "completed_restore_publications": 0,
               "paid_execution": False, "real_provider_requests": 0, "human_mastery": "not_assessed"}
    write(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    output = parser.parse_args().output.resolve()
    summary = run(output)
    print(json.dumps({"status": summary["status"], "output": str(output),
                      "summary_sha256": digest_bytes((output / "summary.json").read_bytes())}))


if __name__ == "__main__":
    main()
