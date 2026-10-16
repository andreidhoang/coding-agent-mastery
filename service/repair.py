"""Oracle-free, supported repository repair on the existing authority runtime."""

from __future__ import annotations

import math
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from .artifacts import LocalArtifacts, canonical_bytes, digest_json
from .contracts import strict_int
from .execution import Workspace, materialize, tree_digest
from .harness import Harness
from .integration import candidate_manifest
from .recovery import restore_checkpoint
from .repair_provider import ProviderApproval
from .repair_verification import PythonFunctionRecipe
from .repositories import FrozenRepository


def committed_repair_events(store, tenant, task_id, snapshot):
    """Export every committed event through the snapshot frontier, with pagination."""
    target = snapshot["frontier"]["sequence"]
    cursor, result = None, []
    while True:
        page = store.events(tenant, task_id, cursor=cursor, limit=1000)
        if page["service_incarnation"] != snapshot["frontier"]["service_incarnation"]:
            raise RuntimeError("event incarnation differs from saved snapshot")
        events = page["events"]
        for event in events:
            sequence = event["sequence"]
            if sequence > target:
                break
            if type(sequence) is not int or sequence != len(result) + 1:
                raise RuntimeError("event history has a missing prefix, gap or duplicate")
            result.append(event)
        if not events or events[-1]["sequence"] >= target:
            break
        if page["cursor"] == cursor:
            raise RuntimeError("event pagination did not advance")
        cursor = page["cursor"]
    if target and (not result or result[-1]["sequence"] != target):
        raise RuntimeError("event history is incomplete for saved snapshot")
    return result


class RepairEngine:
    """One patch worker; private inputs are outside API-visible evidence storage.

    Verifier and provider dependencies are trusted control-plane configuration.
    Candidate Python never runs in this process. The fixture engine is independent.
    """

    def __init__(self, store, artifacts, run_root, verifier, *, private_inputs=None, environment_backend=None):
        self.store, self.artifacts, self.verifier = store, artifacts, verifier
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.private_inputs = private_inputs or LocalArtifacts(self.run_root / "control-inputs")
        self.environment_backend = environment_backend
        if environment_backend is not None:
            from .environment_recovery import DockerEnvironmentBackend
            from .repair_verification import PythonFunctionVerifier
            if type(environment_backend) is not DockerEnvironmentBackend or type(verifier) is not PythonFunctionVerifier or verifier._mock:
                raise ValueError("journal opt-in requires actual local Docker function verifier")

    def submit(
        self, repository: FrozenRepository, recipe: PythonFunctionRecipe, approval: ProviderApproval,
        issue: str, *, tenant="repair", key, budget_units: int,
        execution_deadline: float, review_deadline: float,
        max_turns=12, max_worker_tests=4, context_bytes=131072,
    ) -> dict:
        strict_int(budget_units, "budget_units")
        strict_int(max_turns, "max_turns", 1, 100)
        strict_int(max_worker_tests, "max_worker_tests", 1, 8)
        if not isinstance(issue, str) or not issue.strip() or len(issue) > 8192:
            raise ValueError("bounded issue text required")
        public = recipe.public_description()
        if set(recipe.as_dict()["source_paths"]) != set(repository.files):
            raise ValueError("recipe and frozen repository paths differ")
        self._validate_source(dict(repository.files), recipe)
        inputs = {
            "schema": 1, "repository": repository.as_dict(), "recipe": recipe.as_dict(),
            "provider": approval.as_dict(), "issue": issue,
        }
        input_digest = digest_json(inputs)
        public_metadata = {k: v for k, v in public.items() if k != "worker_cases"}
        requirements = [
            issue,
            "Supported repository source paths: " + ", ".join(sorted(repository.files)),
            "Public function interface: " + canonical_bytes(public_metadata).decode(),
        ] + ["Public test case: " + canonical_bytes(case).decode() for case in public["worker_cases"]]
        contract = {
            "repo_id": repository.repo_id, "base_revision": repository.tree_digest,
            "requirements": requirements,
            "capabilities": ["read_file", "search", "replace_text", "run_tests", "finish"],
            "profile": "production", "patch_slot_limit": 1, "max_nodes": 1, "max_attempts": 10,
            "budget_units": budget_units, "execution_deadline": execution_deadline,
            "review_deadline": review_deadline, "model": approval.model,
            "rate_snapshot": approval.rate_snapshot,
            "grader_digest": recipe.grader_digest,
            "environment_digest": self.verifier.environment_for(recipe),
            "repair_spec": {
                "schema": 1, "input_digest": input_digest,
                "repository_digest": repository.manifest_digest, "recipe_digest": recipe.grader_digest,
                "provider_digest": approval.digest, "max_turns": max_turns,
                "max_worker_tests": max_worker_tests, "context_bytes": context_bytes,
            },
        }
        task = self.store.submit(tenant, key, contract)
        ref = self.private_inputs.put_json(tenant, task["task_id"], inputs)
        if ref["digest"] != input_digest:
            raise ValueError("private input identity mismatch")
        self.store.set_graph(tenant, task["task_id"], task["generation"], [{
            "node_id": "repair", "dependencies": [], "role": "patch",
            "allowed_paths": list(repository.allowed_paths),
        }])
        return task

    def _inputs(self, tenant, task_id):
        task = self.store.get_task(tenant, task_id)
        contract = task["contract"]
        spec = contract.get("repair_spec")
        if not isinstance(spec, dict):
            raise ValueError("task is not a supported repository repair")
        raw = self.private_inputs.get_json(tenant, task_id, spec["input_digest"])
        if not isinstance(raw, dict) or set(raw) != {"schema", "repository", "recipe", "provider", "issue"}:
            raise ValueError("invalid frozen repair input")
        if type(raw["schema"]) is not int or raw["schema"] != 1:
            raise ValueError("unsupported repair input schema")
        repo = FrozenRepository.from_dict(raw["repository"])
        recipe = PythonFunctionRecipe.from_dict(raw["recipe"])
        approval = ProviderApproval.from_dict(raw["provider"])
        if (
            repo.manifest_digest != spec["repository_digest"]
            or recipe.grader_digest != spec["recipe_digest"]
            or approval.digest != spec["provider_digest"]
            or repo.tree_digest != contract["base_revision"]
            or repo.repo_id != contract["repo_id"]
            or recipe.grader_digest != contract["grader_digest"]
            or self.verifier.environment_for(recipe) != contract["environment_digest"]
            or approval.model != contract["model"]
            or approval.rate_snapshot != contract["rate_snapshot"]
        ):
            raise ValueError("frozen repair configuration drift")
        return task, repo, recipe, approval

    @staticmethod
    def _validate_source(files, recipe):
        config = recipe.as_dict()
        if set(files) != set(config["source_paths"]):
            raise ValueError("candidate paths differ from frozen recipe")
        lengths = [len(text.encode()) for text in files.values() if isinstance(text, str)]
        if len(lengths) != len(files):
            raise ValueError("candidate sources must be text")
        if (any(n > config["limits"]["max_file_bytes"] for n in lengths)
                or sum(lengths) > config["limits"]["max_source_bytes"]):
            raise ValueError("candidate exceeds frozen recipe source limits")

    def _checks(self, tenant, task_id, files, recipe, purpose):
        frozen = dict(files)
        self._validate_source(frozen, recipe)
        task = self.store.get_task(tenant, task_id)
        snapshot = self.store.snapshot(tenant, task_id)
        ordinal = sum(s.get("kind") == "verifier" for s in snapshot["sandboxes"])
        reservation = self.store.reserve_environment(
            tenant, task_id, task["generation"], "verifier", f"repair-{purpose}-{ordinal}"
        )
        if reservation.get("duplicate"):
            raise RuntimeError("test environment requires reconciliation before reuse")
        lifecycle = None
        if self.environment_backend is not None:
            from .environment_recovery import EnvironmentLifecycle
            lifecycle = EnvironmentLifecycle(self.store, self.artifacts, tenant, task_id,
                                             reservation["sandbox_id"], self.environment_backend)
        result = self.verifier.verify(frozen, recipe, purpose=purpose, sandbox_id=reservation["sandbox_id"],
                                      **({"lifecycle": lifecycle} if lifecycle is not None else {}))
        if (
            not isinstance(result, dict) or type(result.get("passed")) is not bool
            or result.get("tree_digest") != tree_digest(frozen)
            or result.get("grader_digest") != task["contract"]["grader_digest"]
            or result.get("environment_digest") != task["contract"]["environment_digest"]
            or result.get("phase") != purpose
        ):
            raise RuntimeError("test result identity mismatch; environment retained")
        retirement = result.get("retirement", {})
        ref = self.artifacts.put_json(tenant, task_id, result)
        if not isinstance(retirement, dict) or retirement.get("retired") is not True:
            raise RuntimeError("test environment retirement unconfirmed; environment retained")
        if lifecycle is not None:
            lifecycle.close()
        else:
            retired_ref = self.artifacts.put_json(tenant, task_id, retirement)
            self.store.retire_sandbox(tenant, reservation["sandbox_id"], retired_ref)
        return result, ref

    def run_task(self, tenant, task_id, model=None, *, resume=False, pause_after_turn=None):
        task, repo, recipe, approval = self._inputs(tenant, task_id)
        contract, spec = task["contract"], task["contract"]["repair_spec"]
        snapshot = self.store.snapshot(tenant, task_id)
        if task["execution_state"] in {"review_eligible", "verified_pending_review", "accepted", "completed"}:
            return self._snapshot(tenant, task_id, approval)
        if task["execution_state"] in {"cancelled", "failed"}:
            raise ValueError("repair execution authority is terminal")
        if any(s["status"] != "retired" for s in snapshot["sandboxes"]):
            raise RuntimeError("previous environment retirement requires reconciliation")
        if any(d["effect_state"] in {"in_flight", "unknown"} for d in snapshot["dispatches"]):
            raise RuntimeError("unresolved effects require reconciliation; no replay permitted")
        if any(d["billing_state"] != "settled" for d in snapshot["dispatches"]):
            raise RuntimeError("unresolved billing requires reconciliation; no replay permitted")
        node = next(n for n in snapshot["nodes"] if n["node_id"] == "repair")
        candidate_id = node.get("candidate_id") if node["status"] == "completed" else None
        restored = None
        if candidate_id is None:
            if model is None or not approval.matches(model) or not model.enabled:
                raise PermissionError("explicit adapter matching frozen provider approval required")
            if snapshot["attempts"]:
                if not resume:
                    raise ValueError("interrupted repair requires explicit resume")
                if not snapshot["checkpoints"]:
                    raise RuntimeError("interrupted repair lacks supported clean checkpoint")
                checkpoint = max(snapshot["checkpoints"], key=lambda c: (
                    len(c["dispatch_frontier"]), c["manifest"]["next_turn"], c["created_at"]
                ))
                frontier = set(checkpoint["dispatch_frontier"])
                if any(d["dispatch_id"] not in frontier for d in snapshot["dispatches"]):
                    raise RuntimeError("post-checkpoint effects across attempts require reconciliation")
                restored = restore_checkpoint(self.store, self.artifacts, tenant, task_id, checkpoint["checkpoint_id"])
            budget = snapshot["budget"]
            reserve = budget["limit"] - budget["spent"] - budget["reserved"]
            lease = min(86400, max(1, math.ceil(contract["execution_deadline"] - time.time())))
            grant = self.store.claim(tenant, task_id, "repair", "repair-" + uuid.uuid4().hex, reserve, lease)
            owner = grant["owner"]
            directory = Path(tempfile.mkdtemp(prefix="repair-worker-", dir=self.run_root))
            try:
                materialize(directory, restored["files"] if restored else dict(repo.files))
                limits = recipe.as_dict()["limits"]
                workspace = Workspace(directory, list(repo.allowed_paths),
                                      max_file_bytes=min(131072, limits["max_file_bytes"]),
                                      max_total_bytes=min(262144, limits["max_source_bytes"]))

                def worker_tests(current_files):
                    used = sum(d["kind"] == "run_tests" for d in self.store.snapshot(tenant, task_id)["dispatches"])
                    if used > spec["max_worker_tests"]:
                        raise ValueError("cumulative worker-test limit exhausted")
                    return self._checks(tenant, task_id, current_files, recipe, "worker")[0]

                result = Harness(
                    self.store, self.artifacts, max_turns=spec["max_turns"],
                    context_bytes=spec["context_bytes"], provider_envelopes={approval.model: approval.rate_snapshot},
                ).run(owner, contract, workspace, model, worker_tests, restored=restored,
                      pause_after_turn=pause_after_turn)
                if result["status"] == "paused":
                    return_value = {"paused": True, "checkpoint_id": result["checkpoint_id"]}
                else:
                    manifest = candidate_manifest(dict(repo.files), workspace.snapshot(), list(repo.allowed_paths),
                                                  owner, contract["requirements"])
                    manifest["environment_digest"] = contract["environment_digest"]
                    manifest["manifest_digest"] = digest_json({k: v for k, v in manifest.items()
                                                               if k != "manifest_digest"})
                    ref = self.artifacts.put_json(tenant, task_id, manifest)
                    candidate_id = self.store.accept_candidate(owner, {**manifest, "artifact_ref": ref})["candidate_id"]
                    return_value = None
            finally:
                shutil.rmtree(directory)
                if directory.exists():
                    raise RuntimeError("controlled worker workspace retirement unconfirmed")
                retired = self.artifacts.put_json(tenant, task_id, {
                    "schema": 1, "kind": "controlled-text-workspace-retirement",
                    "sandbox_id": grant["sandbox_id"], "retired": True,
                    "candidate_processes": "none; execution occurs in separately accounted containers",
                })
                self.store.retire_sandbox(tenant, grant["sandbox_id"], retired)
            if return_value:
                return {**self._snapshot(tenant, task_id, approval), **return_value}
        snapshot = self.store.snapshot(tenant, task_id)
        candidate = next(c for c in snapshot["candidates"] if c["candidate_id"] == candidate_id)
        manifest = candidate["manifest"]
        files = manifest["files"]
        if not task["head_candidate_id"]:
            integrated = candidate_manifest(dict(repo.files), files, list(repo.allowed_paths), {},
                                            contract["requirements"], [manifest["manifest_digest"]])
            integrated["environment_digest"] = contract["environment_digest"]
            integrated["manifest_digest"] = digest_json({k: v for k, v in integrated.items()
                                                        if k != "manifest_digest"})
            ref = self.artifacts.put_json(tenant, task_id, integrated)
            head = self.store.integrate(tenant, task_id, task["generation"], [candidate_id], 0,
                                        {**integrated, "artifact_ref": ref})
        else:
            head = {"candidate_id": task["head_candidate_id"], "revision": task["head_revision"]}
            existing = next(c for c in snapshot["candidates"] if c["candidate_id"] == head["candidate_id"])
            if existing["tree_digest"] != tree_digest(files):
                raise ValueError("current head differs from completed repair candidate")
        existing_receipts = [v for v in self.store.snapshot(tenant, task_id)["verifications"] if (
            v["generation"] == task["generation"] and v["candidate_id"] == head["candidate_id"]
            and v["tree_digest"] == tree_digest(files) and v["grader_digest"] == contract["grader_digest"]
            and v["environment_digest"] == contract["environment_digest"]
            and v["contract_digest"] == task["contract_digest"]
        )]
        if existing_receipts:
            receipt = max(existing_receipts, key=lambda v: (v["recorded_at"], v["outcome"] != "pass"))
            ref = receipt["evidence_ref"]
            result = self.artifacts.get_json(tenant, task_id, ref["digest"])
            if (result.get("phase") != "final" or result.get("outcome") != receipt["outcome"]
                    or result.get("tree_digest") != receipt["tree_digest"]
                    or result.get("grader_digest") != receipt["grader_digest"]
                    or result.get("environment_digest") != receipt["environment_digest"]
                    or type(result.get("passed")) is not bool
                    or result["passed"] != (receipt["outcome"] == "pass")
                    or result.get("retirement", {}).get("retired") is not True):
                raise RuntimeError("retained final receipt conflicts with immutable result")
        else:
            result, ref = self._checks(tenant, task_id, files, recipe, "final")
            receipt = self.store.record_verification(
                tenant, task_id, task["generation"], head["candidate_id"], tree_digest(files),
                contract["grader_digest"], contract["environment_digest"], result["outcome"], ref,
            )
        if result["passed"]:
            self.store.publish_review(tenant, task_id, task["generation"], head["candidate_id"],
                                      receipt["verification_id"], head["revision"])
        else:
            self.store.fail_execution(tenant, task_id, task["generation"],
                                      "infrastructure_failed" if result["outcome"] == "error" else "candidate_failed", ref)
        return self._snapshot(tenant, task_id, approval)

    def _snapshot(self, tenant, task_id, approval):
        snapshot = self.store.snapshot(tenant, task_id)
        snapshot["evidence_kind"] = (
            "native_mock_transport_supported_repair" if approval.as_dict()["evidence"]["kind"] == "mock"
            else "operator_configured_provider_repair; inspect actual request receipts"
        )
        snapshot["repair_scope"] = "supported stateless Python functions; human review remains separate"
        return snapshot
