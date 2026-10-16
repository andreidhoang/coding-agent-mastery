import copy
import unittest
from decimal import Decimal

from evals.allocation import Allocation
from evals.analysis import analyze
from evals.fixtures import accepted_fixture, demo_manifest
from evals.manifest import FrozenManifest, assigned_rows


class ManifestTests(unittest.TestCase):
    def test_216_pilot_rows_randomization_and_identity(self):
        frozen = demo_manifest(tasks_count=36, trials=3, arms=("bare", "coordinated_n2"))
        data = frozen.read()
        self.assertEqual(len(data["planned_rows"]), 216)
        self.assertEqual(data["planned_rows"], assigned_rows(data["tasks"], 3, data["arms"], 17))
        self.assertNotEqual(data["planned_rows"], assigned_rows(data["tasks"], 3, data["arms"], 18))
        data["envelope"]["usd"] = 999
        self.assertEqual(frozen.read()["envelope"]["usd"], 20)  # No mutable escape from frozen bytes.

    def test_reject_missing_resources_mismatched_grader_and_duplicate(self):
        original = demo_manifest().read()
        cases = []
        missing = copy.deepcopy(original)
        del missing["envelope"]["ram_bytes"]
        cases.append(missing)
        mismatch = copy.deepcopy(original)
        mismatch["planned_rows"][0]["grader_digest"] = "different"
        cases.append(mismatch)
        duplicate = copy.deepcopy(original)
        duplicate["planned_rows"][-1] = duplicate["planned_rows"][0]
        cases.append(duplicate)
        alias = copy.deepcopy(original)
        alias["treatments"]["coordinated_n1"]["profile_id"] = "bare"
        cases.append(alias)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                FrozenManifest.freeze(data)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.frozen = demo_manifest(tasks_count=2, trials=2, arms=("bare", "coordinated_n2"))
        self.rows = self.frozen.read()["planned_rows"]

    def test_missing_infra_unknown_rows_remain_zero_with_hand_paired_oracle(self):
        # Task0: A=[1,0], B=[1,1]; Task1: A=[0,0], B=[1,0]. Both task deltas=1/2.
        outcomes = []
        for row in self.rows:
            if (
                row["arm"] == "bare"
                and row["task_id"] == "synthetic_task_0"
                and row["trial_id"] == 0
                or row["arm"] == "coordinated_n2"
                and (row["task_id"] == "synthetic_task_0" or row["trial_id"] == 0)
            ):
                outcomes.append(accepted_fixture(row))
            elif row["arm"] == "bare" and row["task_id"] == "synthetic_task_1":
                outcomes.append(
                    {
                        "row_id": row["row_id"],
                        "recorded_at": 50,
                        "status": "infrastructure_failed",
                        "settled_usd": 2,
                    }
                )
            elif row["arm"] == "coordinated_n2":
                outcomes.append(
                    {"row_id": row["row_id"], "recorded_at": 50, "status": "effect_unknown", "unknown_usd": 3}
                )
        report = analyze(self.frozen, outcomes, bootstrap=50)
        self.assertEqual(report["rates"]["bare"]["assigned"], 4)
        self.assertEqual(report["rates"]["bare"]["rate"], 0.25)
        self.assertEqual(report["rates"]["coordinated_n2"]["rate"], 0.75)
        self.assertEqual(report["paired"]["delta"], 0.5)
        self.assertEqual(report["paired"]["interval_95"], [0.5, 0.5])
        self.assertEqual(report["counts"]["reasons"]["missing"], 1)
        self.assertEqual(report["accounting"]["total_exposure_usd"], 11)
        self.assertEqual(report["cost_per_accepted"], 2)
        self.assertFalse(report["study_complete"])
        self.assertEqual(report["completion_curves"]["coordinated_n2"][-1]["fraction"], 0.75)
        self.assertEqual(report["strata"]["repository"]["synthetic_repo_0"]["bare"]["assigned"], 4)

    def test_cutoff_stale_receipt_late_decision_review_and_withdrawal(self):
        row = self.rows[0]
        for update in (
            {"verified_digest": "old-tree"},
            {"eligibility_decision_at": 101, "eligibility_committed_at": 102, "review_at": 103},
            {"review_at": 151, "recorded_at": 151},
            {"withdrawn_at": 150, "recorded_at": 150},
            {"recorded_at": 201},
            {"eligibility_receipt": ""},
        ):
            with self.subTest(update=update):
                report = analyze(self.frozen, [accepted_fixture(row, **update)], bootstrap=10)
                self.assertEqual(report["counts"]["accepted"], 0)
                self.assertIsNone(report["cost_per_accepted"])

    def test_append_only_revisions_resolve_without_backdating_prior_cutoff(self):
        row = self.rows[0]
        initial = {
            "row_id": row["row_id"],
            "result_id": "v1",
            "recorded_at": 50,
            "status": "effect_unknown",
            "unknown_usd": 3,
        }
        late = accepted_fixture(row, result_id="v2", supersedes_id="v1", recorded_at=201)
        report = analyze(self.frozen, [initial, late], bootstrap=10)
        self.assertEqual(report["counts"]["accepted"], 0)
        self.assertEqual(report["accounting"]["unknown_usd"], 3)
        correction = accepted_fixture(row, result_id="v2", supersedes_id="v1", recorded_at=150)
        report = analyze(self.frozen, [initial, correction], bootstrap=10)
        self.assertEqual(report["counts"]["accepted"], 1)
        self.assertEqual(report["accounting"]["unknown_usd"], 0)
        self.assertEqual(report["accounting"]["settled_usd"], 1)
        with self.assertRaises(ValueError):
            analyze(self.frozen, [initial, dict(correction, supersedes_id="absent")])

    def test_repository_resampling_preserves_whole_blocks(self):
        frozen = demo_manifest(tasks_count=4, trials=3, arms=("bare", "coordinated_n2"))
        outcomes = [
            accepted_fixture(r)
            for r in frozen.read()["planned_rows"]
            if r["arm"] == "coordinated_n2" and r["task_id"] in {"synthetic_task_0", "synthetic_task_1"}
        ]
        report = analyze(frozen, outcomes, bootstrap=100, seed=19, cluster="repository")
        self.assertEqual(report["paired"]["clusters"], 2)
        self.assertEqual(report["paired"]["delta"], 0.5)
        self.assertEqual(report["paired"]["interval_95"], [0.0, 1.0])
        self.assertEqual(report, analyze(frozen, outcomes, bootstrap=100, seed=19, cluster="repository"))

    def test_exclusion_is_whole_task_and_preserves_spend(self):
        outcomes = [accepted_fixture(r) for r in self.rows]
        report = analyze(
            self.frozen,
            outcomes,
            bootstrap=10,
            exclusion_ledger=[
                {
                    "task_id": "synthetic_task_0",
                    "reason": "invalid grader",
                    "adjudication_receipt": "blind-review",
                }
            ],
        )
        self.assertEqual(report["counts"]["assigned"], 4)
        self.assertEqual(report["accounting"]["settled_usd"], 8)
        self.assertEqual(report["cost_per_accepted"], 2)
        with self.assertRaises(ValueError):
            analyze(self.frozen, outcomes + [outcomes[0]])


class AllocationTests(unittest.TestCase):
    def test_unknown_floor_and_conserved_envelope(self):
        allocation = Allocation.static(
            20, 2, {"coordinator": 2, "integration": 2, "verification": 2, "cleanup": 2}
        )
        allocation.observe_exposure("worker_0", settled=1, reserved=1, unknown=2)
        observations = [
            {
                "worker_id": "worker_0",
                "observation_id": "done",
                "observed_at": 1,
                "state": "complete",
                "estimated_remaining_usd": 0,
            },
            {
                "worker_id": "worker_1",
                "observation_id": "need",
                "observed_at": 1,
                "state": "running",
                "estimated_remaining_usd": 20,
            },
        ]
        decision = allocation.progress_aware(observations, 1)
        self.assertEqual(allocation.workers["worker_0"].allowance, Decimal(4))
        self.assertEqual(allocation.workers["worker_1"].allowance, Decimal(8))
        self.assertEqual(
            sum(w.allowance for w in allocation.workers.values()) + sum(allocation.reserves.values()),
            Decimal(20),
        )
        self.assertEqual(decision["observation_ids"], ["done", "need"])
        observations[0]["observed_at"] = 2
        with self.assertRaises(ValueError):
            allocation.progress_aware(observations, 1)
        with self.assertRaises(ValueError):
            allocation.observe_exposure("worker_0", settled=3, reserved=0, unknown=2)
