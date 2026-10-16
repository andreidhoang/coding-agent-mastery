"""Typed skills checkpoint proof, reconstructed iteratively from original receipts."""
from __future__ import annotations

from copy import deepcopy

from .artifacts import canonical_bytes, digest_json
from .contracts import digest
from .recovery import _closed, _context_ref, validate_context_checkpoint, validate_context_manifest
from .skill_disclosure import _fail, reconstruct_history, state_value, validate_state_artifacts


def validate_skills_checkpoint_artifacts(artifacts, tenant, task, manifest, payload):
    """Closed byte validation only; no caller-supplied object grants authority."""
    context = validate_context_checkpoint(artifacts, tenant, task, manifest, payload)
    if manifest["schema"] != 3:
        raise ValueError("accepted skills require schema3 checkpoint")
    post = manifest["skills_after_turn"]
    _closed(post, {"state_ref", "state_digest"}, "skills post-turn state")
    digest(post["state_digest"], "post-turn state digest")
    if post["state_ref"].get("digest") != post["state_digest"]:
        _fail()
    accepted = deepcopy(context["acceptance"]["manifest"])
    accepted["skills_state_ref"], accepted["skills_state_digest"] = post["state_ref"], post["state_digest"]
    accepted["binding"]["skills_state_digest"] = post["state_digest"]
    after = validate_state_artifacts(artifacts, tenant, task, accepted)
    before = validate_context_manifest(artifacts, tenant, task, context["acceptance"]["manifest"])
    if after["skills_capture"] != before["skills_capture"] or after["skills_config"] != before["skills_config"]:
        _fail()
    # Check the complete references even when get_json would otherwise accept only a digest.
    raw = _context_ref(artifacts, tenant, task, manifest["artifact_ref"])
    if canonical_bytes(payload) != raw:
        _fail()
    files_raw = _context_ref(artifacts, tenant, task, manifest["workspace_ref"])
    from .protocol import strict_json
    files = strict_json(files_raw.decode("utf-8"), artifacts.max_bytes)
    if not isinstance(files, dict):
        _fail()
    return {"context": context, "before": before, "after": after, "files": files}


def validate_skills_checkpoint(proof, artifacts, checkpoint, *, require_frontier=True, payload=None):
    owner, manifest = checkpoint["owner"], checkpoint["manifest"]
    tenant, task = owner["tenant_id"], owner["task_id"]
    if (checkpoint.get("contract", proof["contract"]) != proof["contract"]
            or owner["generation"] != proof["generation"]):
        _fail()
    if payload is None:
        payload = artifacts.get_json(tenant, task, manifest["artifact_ref"]["digest"])
    validated = validate_skills_checkpoint_artifacts(artifacts, tenant, task, manifest, payload)
    context = validated["context"]
    source = next((d for d in proof["dispatches"] if d["dispatch_id"] == context["dispatch_id"]), None)
    if (source is None or source["owner"] != owner or source.get("context_acceptance") != context["acceptance"]):
        _fail()
    rebuilt = reconstruct_history(artifacts, proof, payload["evidence"], validated["before"]["skills_capture"])
    expected_after = state_value(validated["before"]["skills_capture"], rebuilt["loaded"],
                                 context["acceptance"]["manifest"]["source_checkpoint"])
    if rebuilt["messages"] != payload["messages"] or validated["after"]["skills_state"] != expected_after:
        _fail()
    frontier = checkpoint.get("dispatch_frontier", proof["attempt_frontiers"][owner["attempt_id"]])
    if (not isinstance(frontier, list) or len(frontier) != len(set(frontier))
            or checkpoint.get("pending_dispatches", [])):
        _fail()
    relevant = [d for d in proof["dispatches"] if d["owner"] == owner]
    covered = [d for d in relevant if d["dispatch_id"] in frontier]
    if require_frontier and len(covered) != len(relevant):
        raise ValueError("post-checkpoint effects require explicit reconciliation; cannot rewind")
    if any(d["dispatch_id"] not in rebuilt["represented"] or d["effect_state"] not in {"succeeded", "failed_known"}
           or d["billing_state"] != "settled" for d in covered):
        _fail()
    models = [d for d in covered if d["kind"].startswith("model.")]
    if not models or max(models, key=lambda d: d["context_acceptance"]["accepted_sequence"])["dispatch_id"] != source["dispatch_id"]:
        _fail()
    return {"contract_digest": digest_json(proof["contract"]), "messages": deepcopy(payload["messages"]),
            "evidence": deepcopy(payload["evidence"]), "next_turn": manifest["next_turn"],
            "workspace_digest": digest_json(validated["files"]), "files": validated["files"],
            "source_checkpoint": checkpoint.get("checkpoint_id"),
            "completion_proposed": payload["status"] == "completion_proposed", "context": deepcopy(context),
            "skills_after_turn": deepcopy(manifest["skills_after_turn"]),
            "skills_state": deepcopy(validated["after"]["skills_state"]),
            "authority": "caller must separately acquire a current owner; this data grants none"}


def validate_seed_proof(proof, artifacts, *, require_frontier=True):
    """Validate each ancestor at its own cut; the imported seed also cannot rewind."""
    result = None
    for checkpoint in sorted(proof["checkpoints"], key=lambda k: k["manifest"]["next_turn"]):
        if checkpoint["checkpoint_id"] != proof["source_checkpoint"]:
            descendants = [k for k in proof["checkpoints"] if
                k["manifest"]["context"]["acceptance"]["manifest"]["source_checkpoint"] == checkpoint["checkpoint_id"]]
            for descendant in descendants:
                cut = set(checkpoint.get("dispatch_frontier", []))
                at_descendant = set(descendant.get("dispatch_frontier", []))
                if any(d["owner"] == checkpoint["owner"] and d["dispatch_id"] in at_descendant
                       and d["dispatch_id"] not in cut for d in proof["dispatches"]):
                    raise ValueError("historical effects existed after seed cut before descendant acceptance")
        validated = validate_skills_checkpoint(proof, artifacts, checkpoint,
            require_frontier=require_frontier and checkpoint["checkpoint_id"] == proof["source_checkpoint"])
        if checkpoint["checkpoint_id"] == proof["source_checkpoint"]:
            result = validated
    if proof["source_checkpoint"] is not None and result is None:
        _fail()
    return result


def restore_skills_checkpoint(store, artifacts, tenant, task, checkpoint_id):
    proof = store.read_skills_checkpoint(tenant, task, checkpoint_id)
    result = validate_seed_proof(proof, artifacts)
    if result is None:
        _fail()
    return result
