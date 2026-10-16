"""Clearly synthetic identities for runnable instrument demonstrations, not real task registry."""

from .manifest import ARMS, FrozenManifest, assigned_rows


def demo_manifest(
    *, tasks_count=4, trials=3, arms=("bare", "coordinated_n1", "coordinated_n2", "coordinated_n4"), seed=17
):
    tasks = [
        {
            "task_id": f"synthetic_task_{i}",
            "spec_revision": "synthetic-spec-v1",
            "repository": f"synthetic_repo_{i // 2}",
            "base_commit": "synthetic-base-not-a-git-commit",
            "grader_digest": "synthetic-grader-v1",
            "tier": ("T1", "T2", "T3")[i % 3],
            "version_block": "synthetic-time-model-block",
            "allowed_paths": ["fixture.py"],
            "allowed_capabilities": ["trusted_fixture"],
            "inclusion": "valid",
            "review_rubric": "synthetic-positive-review-required",
            "execution_limit_seconds": 100,
            "provenance": "generated instrument fixture",
            "contamination": "not a capability benchmark",
        }
        for i in range(tasks_count)
    ]
    treatments = {}
    for arm in arms:
        coordinated = int(arm != "bare")
        treatments[arm] = {
            "profile_id": "research" if coordinated else "bare",
            "patch_slot_limit": ARMS[arm],
            "role_counts": {
                "patch_workers": ARMS[arm],
                "coordinator": coordinated,
                "integrator": coordinated,
                "verifier": 1,
            },
            "allocation_policy": "static-v1",
            "context_policy": "synthetic",
            "retrieval_policy": "synthetic",
            "tool_policy": "trusted-fixture-only",
            "model_id": "scripted-no-live-model",
            "model_revision": "scripted-v1",
            "generation_settings": {"temperature": 0},
            "harness_revision": "reference-v1",
            "schema_revision": "1",
        }
    data = {
        "experiment_id": "synthetic-reference-demo-v1",
        "hypothesis": "synthetic arithmetic illustration only",
        "primary_contrast": [arms[0], arms[-1]],
        "primary_endpoint": "accepted_at_cutoff",
        "split": "development",
        "registry_digest": "synthetic-registry-v1",
        "analysis_revision": "paired-v1",
        "assignment_seed": seed,
        "trials": trials,
        "arms": list(arms),
        "tasks": tasks,
        "planned_rows": assigned_rows(tasks, trials, arms, seed),
        "stop_rules": ["boundary violation", "fixed assigned table"],
        "owner": "AI reference fixture",
        "freeze_time": "2026-10-08T00:00:00Z",
        "analysis_cutoff": 200,
        "review_cutoff": 150,
        "envelope": {
            "usd": 20,
            "input_tokens": 10000,
            "output_tokens": 10000,
            "call_concurrency": 2,
            "cpu_seconds": 1000,
            "cpu_cores": 4,
            "ram_bytes": 1000000,
            "disk_bytes": 10000000,
            "process_limit": 20,
            "network_policy": "denied",
            "deadline_seconds": 100,
            "cleanup_reserve_usd": 1,
            "rate_snapshot": "synthetic-zero-provider",
            "per_environment_minimums": {"cpu": 1, "ram_bytes": 100000},
        },
        "environment": {
            "image_digest": "synthetic-image",
            "dependency_digest": "synthetic-deps",
            "architecture": "synthetic",
            "setup_recipe": "none",
            "verifier_digest": "synthetic-verifier",
            "allowed_network": "none",
            "warm_policy": "cold",
            "capacity_evidence": "simulation only; real dispatch not authorized",
        },
        "treatments": treatments,
    }
    return FrozenManifest.freeze(data)


def accepted_fixture(row, **updates):
    result = {
        "row_id": row["row_id"],
        "task_id": row["task_id"],
        "base_commit": row["base_commit"],
        "recorded_at": 120,
        "status": "accepted",
        "cause": "synthetic-fixture-pass",
        "submitted_at": 0,
        "verified_at": 30,
        "eligibility_decision_at": 31,
        "eligibility_committed_at": 32,
        "review_at": 40,
        "candidate_digest": "synthetic-tree",
        "verified_digest": "synthetic-tree",
        "grader_digest": row["grader_digest"],
        "eligibility_receipt": "synthetic-eligibility",
        "review_receipt": "synthetic-review",
        "settled_usd": 1,
        "reserved_usd": 0,
        "unknown_usd": 0,
    }
    result.update(updates)
    return result
