"""Runnable bounded coordinator → isolated patch workers → integrate → verify slice."""

from __future__ import annotations

import concurrent.futures
import shutil
import tempfile
import time
from pathlib import Path

from .artifacts import LocalArtifacts, digest_bytes, digest_json
from .execution import Workspace, materialize, tree_digest
from .harness import Harness
from .integration import candidate_manifest, integrate_candidates
from .protocol import ToolCall
from .providers import ScriptedModel
from .verification import FixtureVerifier, LinuxVerifier


class ReferenceEngine:
    """Scripted fixture model is explicit: mechanics evidence, no learned capability."""

    def __init__(
        self, store, artifacts: LocalArtifacts, run_root: str | Path, sandbox_image: str | None = None,
        *, environment_backend=None,
    ):
        self.store, self.artifacts = store, artifacts
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.verifier = LinuxVerifier(sandbox_image) if sandbox_image else FixtureVerifier()
        self.environment_backend = environment_backend
        if environment_backend is not None:
            from .environment_recovery import DockerEnvironmentBackend
            if type(environment_backend) is not DockerEnvironmentBackend or not isinstance(self.verifier, LinuxVerifier):
                raise ValueError("journal opt-in requires actual local Docker fixture verifier")

    def submit_fixture(
        self, task_definition_id: str, *, tenant: str = "demo", key: str = "demo", workers: int = 2
    ) -> dict:
        from workloads import load_task
        from workloads.registry import TARGET_FILES

        selected = load_task(task_definition_id)
        base = {p: (selected.baseline_path / p).read_text() for p in TARGET_FILES}
        contract = {
            "repo_id": "synthetic-issue-tracker:" + selected.task_id,
            "base_revision": tree_digest(base),
            "requirements": list(selected.requirements),
            "capabilities": ["read_file", "search", "replace_text", "run_tests", "finish"],
            "execution_deadline": time.time() + 600,
            "review_deadline": time.time() + 3600,
            "profile": "production" if workers == 2 else "research",
            "patch_slot_limit": workers,
            "budget_units": 1000,
            "max_nodes": 8,
            "max_attempts": 8,
            "model": "scripted-fixture-v1",
            "grader_digest": selected.as_dict()["grader_sha256"],
            "environment_digest": self.verifier.environment_digest,
        }
        return self.store.submit(tenant, key, contract)

    def run_task(self, tenant_id: str, task_id: str) -> dict:
        from workloads import load_task
        from workloads.registry import ROOT, TARGET_FILES, validate_assets

        task = self.store.get_task(tenant_id, task_id)
        if task["execution_state"] in {"review_eligible", "verified_pending_review", "accepted", "completed"}:
            return self.store.snapshot(tenant_id, task_id)
        validate_assets()
        contract = task["contract"]
        if contract["model"] != "scripted-fixture-v1" or not contract["repo_id"].startswith(
            "synthetic-issue-tracker:"
        ):
            raise ValueError("reference runner admits only declared frozen scripted fixtures")
        try:
            selected = load_task(contract["repo_id"].split(":", 1)[1])
        except KeyError as exc:
            raise ValueError("reference runner requires a registered frozen fixture") from exc
        base = {p: (selected.baseline_path / p).read_text() for p in TARGET_FILES}
        reference = {p: (ROOT / "oracle/reference" / p).read_text() for p in TARGET_FILES}
        if (
            tree_digest(base) != contract["base_revision"]
            or self.verifier.environment_digest != contract["environment_digest"]
            or list(selected.requirements) != contract["requirements"]
            or selected.as_dict()["grader_sha256"] != contract["grader_digest"]
        ):
            raise ValueError("frozen source/requirements/grader/environment drift")
        changed = [p for p in TARGET_FILES if base[p] != reference[p]]
        # The planned graph has one patch node per changed file; concurrency limit is independent.
        nodes = [
            {"node_id": "patch-" + str(index), "dependencies": [], "role": "patch", "allowed_paths": [path]}
            for index, path in enumerate(changed)
        ]
        self.store.set_graph(tenant_id, task_id, task["generation"], nodes)
        prior = self.store.snapshot(tenant_id, task_id)
        completed = {
            node["node_id"]: node["candidate_id"] for node in prior["nodes"] if node["status"] == "completed"
        }
        saved_candidates = {candidate["candidate_id"]: candidate for candidate in prior["candidates"]}

        def worker(node):
            if node["node_id"] in completed:
                identifier = completed[node["node_id"]]
                saved = saved_candidates[identifier]["manifest"]
                return {
                    k: v
                    for k, v in saved.items()
                    if k not in {"artifact_ref", "candidate_id", "dependency_versions"}
                }, identifier
            grant = self.store.claim(
                tenant_id, task_id, node["node_id"], "claim-" + task_id + "-" + node["node_id"], 100, 300
            )
            owner = grant["owner"]
            directory = Path(tempfile.mkdtemp(prefix="worker-", dir=self.run_root))
            try:
                materialize(directory, base)
                workspace = Workspace(directory, node["allowed_paths"])
                path = node["allowed_paths"][0]
                scripted = ScriptedModel(
                    [
                        [ToolCall("read", "read_file", {"path": path})],
                        [
                            ToolCall(
                                "edit",
                                "replace_text",
                                {
                                    "path": path,
                                    "expected_digest": digest_bytes(base[path].encode()),
                                    "old": base[path],
                                    "new": reference[path],
                                },
                            )
                        ],
                        [ToolCall("finish", "finish", {"summary": "scripted fixture edit complete"})],
                    ]
                )
                Harness(self.store, self.artifacts).run(owner, contract, workspace, scripted)
                manifest = candidate_manifest(
                    base, workspace.snapshot(), node["allowed_paths"], owner, contract["requirements"]
                )
                manifest["environment_digest"] = contract["environment_digest"]
                # Environment identity is part of the final manifest content, so recompute its digest.
                manifest["manifest_digest"] = digest_json(
                    {k: v for k, v in manifest.items() if k != "manifest_digest"}
                )
                ref = self.artifacts.put_json(tenant_id, task_id, manifest)
                accepted = self.store.accept_candidate(owner, {**manifest, "artifact_ref": ref})
                return manifest, accepted["candidate_id"]
            finally:
                shutil.rmtree(directory)
                retirement = self.artifacts.put_json(
                    tenant_id,
                    task_id,
                    {
                        "kind": "trusted-fixture-workspace-retirement",
                        "sandbox_id": grant["sandbox_id"],
                        "retired": not directory.exists(),
                        "mode": "no_candidate_process_in_patch_workspace",
                    },
                )
                self.store.retire_sandbox(tenant_id, grant["sandbox_id"], retirement)

        with concurrent.futures.ThreadPoolExecutor(max_workers=contract["patch_slot_limit"]) as pool:
            results = list(pool.map(worker, nodes))
        integrated = integrate_candidates(base, [manifest for manifest, _ in results])
        manifest = candidate_manifest(
            base,
            integrated,
            list(TARGET_FILES),
            {},
            contract["requirements"],
            [manifest["manifest_digest"] for manifest, _ in results],
        )
        manifest["environment_digest"] = contract["environment_digest"]
        manifest["manifest_digest"] = digest_json(
            {k: v for k, v in manifest.items() if k != "manifest_digest"}
        )
        manifest_ref = self.artifacts.put_json(tenant_id, task_id, manifest)
        current = self.store.get_task(tenant_id, task_id)
        if current["head_candidate_id"]:
            existing = next(
                c
                for c in self.store.snapshot(tenant_id, task_id)["candidates"]
                if c["candidate_id"] == current["head_candidate_id"]
            )
            if existing["tree_digest"] != tree_digest(integrated):
                raise ValueError("existing integration differs from reconstructed candidate")
            head = {"candidate_id": existing["candidate_id"], "revision": current["head_revision"]}
        else:
            head = self.store.integrate(
                tenant_id,
                task_id,
                task["generation"],
                [identifier for _, identifier in results],
                0,
                {**manifest, "artifact_ref": manifest_ref},
            )
        auxiliary = self.store.snapshot(tenant_id, task_id)["sandboxes"]
        ordinal = sum(s.get("kind") == "verifier" for s in auxiliary)
        reservation = self.store.reserve_environment(
            tenant_id, task_id, task["generation"], "verifier", f"verify-{task_id}-{ordinal}"
        )
        if reservation.get("duplicate"):
            raise RuntimeError("verifier environment reservation requires reconciliation before reuse")
        lifecycle = None
        if self.environment_backend is not None:
            from .environment_recovery import EnvironmentLifecycle
            lifecycle = EnvironmentLifecycle(self.store, self.artifacts, tenant_id, task_id,
                                             reservation["sandbox_id"], self.environment_backend)
        try:
            verification = self.verifier.verify(integrated, selected, sandbox_id=reservation["sandbox_id"],
                                               **({"lifecycle": lifecycle} if lifecycle is not None else {}))
        finally:
            if isinstance(self.verifier, FixtureVerifier):
                retired = self.artifacts.put_json(
                    tenant_id,
                    task_id,
                    {
                        "kind": "trusted-fixture-verifier-retirement",
                        "sandbox_id": reservation["sandbox_id"],
                        "retired": True,
                        "evidence": "no candidate process or remote environment is created by this backend",
                    },
                )
                self.store.retire_sandbox(tenant_id, reservation["sandbox_id"], retired)
        if isinstance(self.verifier, LinuxVerifier):
            if not verification.get("retirement", {}).get("retired"):
                raise RuntimeError("verifier environment retirement unconfirmed")
            if lifecycle is not None:
                lifecycle.close()
            else:
                retired = self.artifacts.put_json(tenant_id, task_id, verification["retirement"])
                self.store.retire_sandbox(tenant_id, reservation["sandbox_id"], retired)
        evidence_ref = self.artifacts.put_json(tenant_id, task_id, verification)
        # Persist the observation and confirmed cleanup before rejecting false attribution.
        # Requested contract fields cannot stand in for identities measured by the verifier.
        if not isinstance(verification, dict) or type(verification.get("passed")) is not bool:
            raise ValueError("verifier must return a strict boolean verdict")
        expected_identities = {
            "tree_digest": tree_digest(integrated),
            "grader_digest": contract["grader_digest"],
            "environment_digest": contract["environment_digest"],
        }
        if any(verification.get(field) != expected for field, expected in expected_identities.items()):
            raise ValueError("verifier tree/grader/environment identity mismatch")
        receipt = self.store.record_verification(
            tenant_id,
            task_id,
            task["generation"],
            head["candidate_id"],
            verification["tree_digest"],
            verification["grader_digest"],
            verification["environment_digest"],
            "pass" if verification["passed"] else "fail",
            evidence_ref,
        )
        if verification["passed"]:
            self.store.publish_review(
                tenant_id,
                task_id,
                task["generation"],
                head["candidate_id"],
                receipt["verification_id"],
                head["revision"],
            )
        else:
            self.store.fail_execution(
                tenant_id, task_id, task["generation"], "candidate_failed", evidence_ref
            )
        snapshot = self.store.snapshot(tenant_id, task_id)
        snapshot["verification_detail"] = verification
        snapshot["evidence_kind"] = "scripted_mechanics_not_model_capability"
        return snapshot
