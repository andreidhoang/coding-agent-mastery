"""EV-02: immutable JSON identity and complete preassigned attempts."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass

from .validation import count, finite_real

ARMS = {"bare": 1, "coordinated_n1": 1, "coordinated_n2": 2, "coordinated_n4": 4}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _required(obj, names, label):
    for name in names.split():
        if name not in obj or obj[name] is None or obj[name] == "":
            raise ValueError(f"{label}: missing {name}")


def _positive(obj, names):
    for name in names.split():
        finite_real(obj[name], name, positive=True)


def assigned_rows(tasks, trials, arms, seed):
    """Randomize arm order within complete task/trial/time-version blocks."""
    count(trials, "trials", 1)
    count(seed, "assignment_seed")
    if not arms or len(set(arms)) != len(arms) or set(arms) - ARMS.keys():
        raise ValueError("invalid trials or arms")
    rng = random.Random(seed)
    rows = []
    for task in sorted(tasks, key=lambda t: (t["tier"], t["version_block"], t["task_id"])):
        for trial in range(trials):
            order = list(arms)
            rng.shuffle(order)
            for arm in order:
                rows.append(
                    {
                        "row_id": f"{task['task_id']}:{trial}:{arm}",
                        "task_id": task["task_id"],
                        "trial_id": trial,
                        "arm": arm,
                        "schedule_index": len(rows),
                        "base_commit": task["base_commit"],
                        "grader_digest": task["grader_digest"],
                        "version_block": task["version_block"],
                        "submission_id": f"{task['task_id']}:{trial}:{arm}",
                    }
                )
    return rows


def validate(data):
    _required(
        data,
        "experiment_id hypothesis primary_contrast primary_endpoint split registry_digest analysis_revision assignment_seed trials arms tasks planned_rows stop_rules owner freeze_time analysis_cutoff review_cutoff envelope environment treatments",
        "experiment",
    )
    if data["split"] not in {"development", "held_out"}:
        raise ValueError("split must be development or held_out")
    _required(
        data["envelope"],
        "usd input_tokens output_tokens call_concurrency cpu_seconds cpu_cores ram_bytes disk_bytes process_limit network_policy deadline_seconds cleanup_reserve_usd rate_snapshot per_environment_minimums",
        "envelope",
    )
    _positive(
        data["envelope"],
        "usd input_tokens output_tokens call_concurrency cpu_seconds cpu_cores ram_bytes disk_bytes process_limit deadline_seconds",
    )
    reserve = data["envelope"]["cleanup_reserve_usd"]
    finite_real(reserve, "cleanup reserve", minimum=0)
    if reserve > data["envelope"]["usd"]:
        raise ValueError("cleanup reserve outside envelope")
    _required(
        data["environment"],
        "image_digest dependency_digest architecture setup_recipe verifier_digest allowed_network warm_policy capacity_evidence",
        "environment",
    )
    for field in ("analysis_cutoff", "review_cutoff"):
        finite_real(data[field], field, minimum=0)
    count(data["trials"], "trials", 1)
    count(data["assignment_seed"], "assignment_seed")
    for field in (
        "input_tokens",
        "output_tokens",
        "call_concurrency",
        "cpu_cores",
        "ram_bytes",
        "disk_bytes",
        "process_limit",
    ):
        count(data["envelope"][field], field, 1)
    arms = data["arms"]
    if not arms or len(set(arms)) != len(arms) or set(arms) - ARMS.keys():
        raise ValueError("unsupported or duplicate arm")
    if (
        len(data["primary_contrast"]) != 2
        or len(set(data["primary_contrast"])) != 2
        or not set(data["primary_contrast"]) <= set(arms)
    ):
        raise ValueError("contrast must name two assigned arms")
    for arm in arms:
        treatment = data["treatments"].get(arm, {})
        _required(
            treatment,
            "profile_id patch_slot_limit role_counts allocation_policy context_policy retrieval_policy tool_policy model_id model_revision generation_settings harness_revision schema_revision",
            arm,
        )
        count(treatment["patch_slot_limit"], "patch_slot_limit", 1)
        for role, value in treatment["role_counts"].items():
            count(value, role)
        if treatment["patch_slot_limit"] != ARMS[arm]:
            raise ValueError("arm worker count mismatch")
        profile = "bare" if arm == "bare" else "research"
        if treatment["profile_id"] != profile:
            raise ValueError("invalid profile")
        expected = {
            "patch_workers": ARMS[arm],
            "coordinator": int(arm != "bare"),
            "integrator": int(arm != "bare"),
            "verifier": 1,
        }
        if treatment["role_counts"] != expected:
            raise ValueError("explicit roles must distinguish bare from coordinated N=1")
    tasks = {}
    for task in data["tasks"]:
        _required(
            task,
            "task_id spec_revision repository base_commit grader_digest tier version_block allowed_paths allowed_capabilities inclusion review_rubric execution_limit_seconds provenance contamination",
            "task",
        )
        _positive(task, "execution_limit_seconds")
        if task["execution_limit_seconds"] > data["envelope"]["deadline_seconds"]:
            raise ValueError("task execution limit exceeds aggregate deadline")
        if task["task_id"] in tasks or task["inclusion"] != "valid" or task["tier"] not in {"T1", "T2", "T3"}:
            raise ValueError("duplicate/invalid task or tier")
        tasks[task["task_id"]] = task
    if not tasks or not isinstance(data["trials"], int) or data["trials"] < 1:
        raise ValueError("empty registry or invalid trials")
    expected = {(t, r, a) for t in tasks for r in range(data["trials"]) for a in arms}
    seen, identities, schedule = set(), set(), set()
    for row in data["planned_rows"]:
        _required(
            row,
            "row_id task_id trial_id arm schedule_index base_commit grader_digest version_block submission_id",
            "row",
        )
        count(row["trial_id"], "trial_id")
        count(row["schedule_index"], "schedule_index")
        key = (row["task_id"], row["trial_id"], row["arm"])
        if (
            key not in expected
            or key in seen
            or row["row_id"] in identities
            or row["submission_id"] in identities
        ):
            # row_id and submission_id may intentionally be equal within one row.
            raise ValueError("duplicate or unplanned assignment")
        task = tasks[row["task_id"]]
        if any(row[k] != task[k] for k in ("base_commit", "grader_digest", "version_block")):
            raise ValueError("assignment base/grader/version mismatch")
        if row["schedule_index"] in schedule:
            raise ValueError("duplicate schedule index")
        seen.add(key)
        identities.update((row["row_id"], row["submission_id"]))
        schedule.add(row["schedule_index"])
    if seen != expected or schedule != set(range(len(expected))):
        raise ValueError("incomplete assignment table")
    canonical(data)


@dataclass(frozen=True)
class FrozenManifest:
    payload: bytes
    digest: str

    @classmethod
    def freeze(cls, data):
        validate(data)
        payload = canonical(data)
        return cls(payload, hashlib.sha256(payload).hexdigest())

    def read(self):
        return json.loads(self.payload)

    def verify(self):
        if hashlib.sha256(self.payload).hexdigest() != self.digest:
            raise ValueError("manifest digest mismatch")
        validate(self.read())
