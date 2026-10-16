"""Run an offline synthetic experiment packet or analyze saved frozen assignments."""

import argparse
import json
from pathlib import Path

from .allocation import Allocation
from .analysis import analyze
from .fixtures import accepted_fixture, demo_manifest
from .manifest import FrozenManifest
from .simulation import Arrival, Node, replay_serving, simulate_dag


def demo():
    frozen = demo_manifest()
    rows = frozen.read()["planned_rows"]
    outcomes = []
    for i, row in enumerate(rows):
        if i % 5 == 0:
            continue  # Deliberately lost assigned rows remain in the denominator.
        if i % 7 == 0:
            outcomes.append(
                {"row_id": row["row_id"], "recorded_at": 120, "status": "effect_unknown", "unknown_usd": 1}
            )
        else:
            outcomes.append(accepted_fixture(row))
    graph = [
        Node("plan", 1, patch_slots=0),
        Node("branch_a", 4, ("plan",)),
        Node("branch_b", 4, ("plan",)),
        Node("integrate", 2, ("branch_a", "branch_b"), patch_slots=0),
    ]
    arrivals = [
        Arrival(
            f"request_{i}",
            i * 0.2,
            100,
            10,
            tool_gap_seconds=1,
            appended_tokens=10,
            prefix_identity="same-synthetic-prefix",
        )
        for i in range(12)
    ]
    allocation = Allocation.static(
        20, 2, {"coordinator": 2, "integration": 2, "verification": 2, "cleanup": 2}
    )
    allocation.observe_exposure("worker_0", settled=1, reserved=0, unknown=2)
    decision = allocation.progress_aware(
        [
            {
                "worker_id": "worker_0",
                "observation_id": "obs-0",
                "observed_at": 1,
                "state": "complete",
                "estimated_remaining_usd": 0,
            },
            {
                "worker_id": "worker_1",
                "observation_id": "obs-1",
                "observed_at": 1,
                "state": "running",
                "estimated_remaining_usd": 10,
            },
        ],
        1,
    )
    return {
        "evidence": "all identities, outcomes and durations are synthetic",
        "manifest": frozen.read(),
        "manifest_digest": frozen.digest,
        "outcomes": outcomes,
        "analysis": analyze(frozen, outcomes),
        "dag_scaling": [simulate_dag(graph, n=n) for n in (1, 2, 4)],
        "serving_scaling": [replay_serving(arrivals, n=n, queue_limit=4) for n in (1, 2, 4)],
        "allocation_decision": decision,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--outcomes", type=Path)
    parser.add_argument("--cluster", choices=("task", "repository"), default="task")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.manifest) != bool(args.outcomes):
        parser.error("--manifest and --outcomes required together")
    if args.manifest:
        packet = json.loads(args.manifest.read_text())
        frozen = FrozenManifest.freeze(packet["manifest"])
        if frozen.digest != packet["manifest_digest"]:
            raise ValueError("saved manifest hash mismatch")
        result = analyze(frozen, json.loads(args.outcomes.read_text()), cluster=args.cluster)
    else:
        result = demo()
    content = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n")
        print(json.dumps({"saved": str(args.output.resolve()), "evidence": result["evidence"]}))
    else:
        print(content)


if __name__ == "__main__":
    main()
