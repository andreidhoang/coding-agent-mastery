"""All-assigned estimands, paired cluster bootstrap and conservative accounting."""

import hashlib
import random
from collections import Counter, defaultdict
from statistics import mean

from .manifest import canonical
from .validation import count, finite_real

STATUSES = {
    "accepted",
    "verified_pending_review",
    "review_rejected",
    "review_deadline_exceeded",
    "candidate_failed",
    "budget_exhausted",
    "deadline_exceeded",
    "cancelled",
    "infrastructure_failed",
    "policy_blocked",
    "effect_unknown",
}


CONSUMED_FIELDS = ("settled_usd", "input_tokens", "output_tokens", "cpu_seconds", "human_review_minutes")
ACCOUNTING_FIELDS = CONSUMED_FIELDS + ("reserved_usd", "unknown_usd")


def _number(value):
    return finite_real(value, "accounting/timestamp", minimum=0)


def _resource(value, field):
    return count(value, field) if field in {"input_tokens", "output_tokens"} else _number(value)


def accepted(result, task, manifest):
    """Trusted receipt must precede DB decision; review and withdrawal are cutoff facts."""
    if result.get("status") != "accepted":
        return 0
    required = (
        "submitted_at",
        "verified_at",
        "eligibility_decision_at",
        "eligibility_committed_at",
        "review_at",
        "task_id",
        "base_commit",
        "candidate_digest",
        "verified_digest",
        "grader_digest",
        "eligibility_receipt",
        "review_receipt",
    )
    if any(k not in result or result[k] is None for k in required):
        return 0
    if any(not isinstance(result[k], str) or not result[k].strip() for k in required[5:]):
        return 0
    times = {k: _number(result[k]) for k in required[:5]}
    cutoff = manifest["analysis_cutoff"]
    decision = times["eligibility_decision_at"]
    execution_limit = _number(times["submitted_at"] + task["execution_limit_seconds"])
    if not (times["submitted_at"] <= times["verified_at"] <= decision <= execution_limit):
        return 0
    if not (
        decision
        <= times["eligibility_committed_at"]
        <= times["review_at"]
        <= min(cutoff, manifest["review_cutoff"])
    ):
        return 0
    if (
        result["task_id"] != task["task_id"]
        or result["base_commit"] != task["base_commit"]
        or result["candidate_digest"] != result["verified_digest"]
        or result["grader_digest"] != task["grader_digest"]
    ):
        return 0
    if result.get("withdrawn_at") is not None and _number(result["withdrawn_at"]) <= cutoff:
        return 0
    return 1


def analyze(frozen, outcomes, *, bootstrap=2000, seed=0, cluster="task", exclusion_ledger=()):
    frozen.verify()
    manifest = frozen.read()
    count(bootstrap, "bootstrap", 1)
    count(seed, "bootstrap seed")
    if cluster not in {"task", "repository"}:
        raise ValueError("invalid bootstrap method")
    tasks = {t["task_id"]: t for t in manifest["tasks"]}
    planned = {r["row_id"]: r for r in manifest["planned_rows"]}
    results, history, result_ids = {}, {}, set()
    for result in outcomes:
        rid = result["row_id"]
        if rid not in planned or result.get("status") not in STATUSES:
            raise ValueError("unknown result or unsupported outcome")
        recorded_at = _number(result["recorded_at"])
        for field in ACCOUNTING_FIELDS:
            _resource(result.get(field, 0), field)
        for field in (
            "submitted_at",
            "verified_at",
            "eligibility_decision_at",
            "eligibility_committed_at",
            "review_at",
            "withdrawn_at",
        ):
            if result.get(field) is not None:
                if _number(result[field]) > recorded_at:
                    raise ValueError(f"{field} cannot be later than recorded_at")
        if result.get("result_id"):
            if result["result_id"] in result_ids:
                raise ValueError("result revision identity reused")
            result_ids.add(result["result_id"])
        if rid in history:
            prior = history[rid]
            for field in CONSUMED_FIELDS:
                if result.get(field, 0) < prior.get(field, 0):
                    raise ValueError(
                        f"cumulative {field} cannot decrease; refunds/cost corrections need a separate unsupported accounting protocol"
                    )
            if (
                not result.get("result_id")
                or not prior.get("result_id")
                or result.get("supersedes_id") != prior["result_id"]
                or result["result_id"] == prior["result_id"]
                or recorded_at <= prior["recorded_at"]
            ):
                raise ValueError("duplicate result or invalid append-only revision chain")
        elif result.get("supersedes_id") is not None:
            raise ValueError("first result cannot supersede absent evidence")
        history[rid] = result
        if recorded_at <= manifest["analysis_cutoff"]:
            results[rid] = result
    excluded = set()
    for record in exclusion_ledger:
        if (
            record.get("task_id") not in tasks
            or not record.get("reason")
            or not record.get("adjudication_receipt")
        ):
            raise ValueError("invalid exclusion adjudication")
        excluded.add(record["task_id"])
    included_rows = [r for r in planned.values() if r["task_id"] not in excluded]
    if not included_rows:
        raise ValueError("no included tasks")
    scores, row_reasons, reasons, accounting, started, completed = {}, {}, Counter(), defaultdict(int), 0, 0
    for row in included_rows:
        result = results.get(row["row_id"], {})
        scores[row["row_id"]] = accepted(result, tasks[row["task_id"]], manifest)
        status = result.get("status", "missing")
        reason = (
            "accepted_claim_without_eligibility"
            if status == "accepted" and not scores[row["row_id"]]
            else status
        )
        row_reasons[row["row_id"]] = reason
        reasons[reason] += 1
        started += int(result.get("submitted_at") is not None)
        completed += int(
            bool(result) and result["status"] not in {"verified_pending_review", "effect_unknown"}
        )
    # Spend on excluded tasks remains experiment spend. Exclusion cannot make bills vanish.
    for result in results.values():
        for field in ACCOUNTING_FIELDS:
            accounting[field] += _resource(result.get(field, 0), field)
            _resource(accounting[field], field)
    accounting["outstanding_exposure_usd"] = accounting["reserved_usd"] + accounting["unknown_usd"]
    accounting["total_exposure_usd"] = accounting["settled_usd"] + accounting["outstanding_exposure_usd"]
    _number(accounting["outstanding_exposure_usd"])
    _number(accounting["total_exposure_usd"])
    rates = {}
    per_task = {}
    for arm in manifest["arms"]:
        rows = [r for r in included_rows if r["arm"] == arm]
        per_task[arm] = {
            tid: mean(scores[r["row_id"]] for r in rows if r["task_id"] == tid)
            for tid in tasks
            if tid not in excluded
        }
        n_accepted = sum(scores[r["row_id"]] for r in rows)
        rates[arm] = {
            "assigned": len(rows),
            "accepted": n_accepted,
            "rate": n_accepted / len(rows),
            "task_averaged_rate": mean(per_task[arm].values()),
        }
    strata = {}
    for dimension in ("tier", "repository"):
        strata[dimension] = {}
        for value in sorted({tasks[r["task_id"]][dimension] for r in included_rows}):
            strata[dimension][value] = {}
            for arm in manifest["arms"]:
                rows = [
                    r for r in included_rows if r["arm"] == arm and tasks[r["task_id"]][dimension] == value
                ]
                strata[dimension][value][arm] = {
                    "assigned": len(rows),
                    "accepted": sum(scores[r["row_id"]] for r in rows),
                    "rate": mean(scores[r["row_id"]] for r in rows),
                }
    a, b = manifest["primary_contrast"]
    differences = {tid: per_task[b][tid] - per_task[a][tid] for tid in per_task[a]}
    groups = defaultdict(list)
    for tid in differences:
        groups[tid if cluster == "task" else tasks[tid]["repository"]].append(tid)
    rng, samples, keys = random.Random(seed), [], sorted(groups)
    for _ in range(bootstrap):
        chosen = [tid for _ in keys for tid in groups[rng.choice(keys)]]
        samples.append(mean(differences[tid] for tid in chosen))
    samples.sort()
    interval = [samples[int((len(samples) - 1) * q)] for q in (0.025, 0.975)]
    events = sorted(
        (results[r["row_id"]]["review_at"] - results[r["row_id"]]["submitted_at"], r["arm"])
        for r in included_rows
        if scores[r["row_id"]]
    )
    curves = {
        arm: [
            {
                "elapsed_seconds": t,
                "fraction": sum(aa == arm and tt <= t for tt, aa in events) / rates[arm]["assigned"],
            }
            for t in sorted({tt for tt, aa in events if aa == arm})
        ]
        for arm in rates
    }
    total_accepted = sum(v["accepted"] for v in rates.values())
    cross_tab = Counter()
    for tid in differences:
        for trial in range(manifest["trials"]):
            pair = [
                next(
                    r
                    for r in included_rows
                    if r["task_id"] == tid and r["trial_id"] == trial and r["arm"] == arm
                )
                for arm in (a, b)
            ]
            cross_tab[f"{scores[pair[0]['row_id']]}{scores[pair[1]['row_id']]}"] += 1
    reasons_by_arm = {
        arm: dict(Counter(row_reasons[r["row_id"]] for r in included_rows if r["arm"] == arm))
        for arm in rates
    }
    sensitivity = {
        arm: {
            "assigned": sum(r["arm"] == arm for r in planned.values()),
            "rate": mean(
                accepted(results.get(r["row_id"], {}), tasks[r["task_id"]], manifest)
                for r in planned.values()
                if r["arm"] == arm
            ),
        }
        for arm in manifest["arms"]
    }
    return {
        "evidence": "offline arithmetic; not live coding capability",
        "manifest_digest": frozen.digest,
        "raw_result_digest": hashlib.sha256(canonical(outcomes)).hexdigest(),
        "cutoff": manifest["analysis_cutoff"],
        "included_row_ids": [r["row_id"] for r in included_rows],
        "excluded_task_ids": sorted(excluded),
        "exclusion_ledger": list(exclusion_ledger),
        "sensitivity_without_exclusion": sensitivity,
        "counts": {
            "assigned": len(included_rows),
            "started": started,
            "completed": completed,
            "accepted": total_accepted,
            "reasons": dict(reasons),
        },
        "study_complete": completed == len(included_rows),
        "rates": rates,
        "strata": strata,
        "paired": {
            "contrast": [a, b],
            "delta": mean(differences.values()),
            "per_task": differences,
            "interval_95": interval,
            "cluster": cluster,
            "clusters": len(keys),
            "bootstrap_seed": seed,
            "repeats": bootstrap,
            "paired_trial_cross_tab_A_B": dict(cross_tab),
        },
        "accounting": dict(accounting),
        "cost_per_accepted": accounting["settled_usd"] / total_accepted if total_accepted else None,
        "completion_curves": curves,
        "reasons_by_arm": reasons_by_arm,
        "limitations": [
            "Tiny fixtures do not establish coverage or powered sample size.",
            "Few repository clusters weakly estimate uncertainty.",
            "Missing and Unknown outcomes contribute zero at cutoff; they retain their labels.",
        ],
    }
