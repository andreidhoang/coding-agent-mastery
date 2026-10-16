import unittest

from evals.simulation import Arrival, Node, replay_serving, simulate_dag


class DagTests(unittest.TestCase):
    def test_chain_no_speedup_and_branches_have_serial_integration(self):
        chain = [Node("a", 3), Node("b", 4, ("a",)), Node("integrate", 2, ("b",), patch_slots=0)]
        self.assertEqual([simulate_dag(chain, n=n)["makespan_seconds"] for n in (1, 2, 4)], [9, 9, 9])
        fanout = [
            Node("plan", 1, patch_slots=0),
            Node("a", 4, ("plan",)),
            Node("b", 4, ("plan",)),
            Node("integrate", 2, ("a", "b"), patch_slots=0),
        ]
        reports = [simulate_dag(fanout, n=n) for n in (1, 2, 4)]
        self.assertEqual([r["makespan_seconds"] for r in reports], [11, 7, 7])
        self.assertEqual([r["dependency_critical_path_seconds"] for r in reports], [7, 7, 7])
        self.assertEqual(reports[0]["realized_critical_path_seconds"], 11)
        self.assertEqual(reports[1]["realized_critical_path_seconds"], 7)
        self.assertEqual(reports[0]["realized_critical_path"], ["plan", "a", "b", "integrate"])
        self.assertEqual(reports[1]["nodes"]["integrate"]["started_at"], 5)
        constrained = simulate_dag(fanout, n=4, cpu_capacity=1)
        self.assertEqual(constrained["makespan_seconds"], 11)
        for report in reports:
            self.assertTrue(all(t["resources_used"]["patch_slots"] <= report["n"] for t in report["trace"]))

    def test_cycle_and_capacity_fail_before_schedule(self):
        for graph in ([Node("a", 1, ("b",)), Node("b", 1, ("a",))], [Node("a", 1, cpu_units=5)]):
            with self.assertRaises(ValueError):
                simulate_dag(graph, n=1)


class ServingTests(unittest.TestCase):
    def test_arrivals_do_not_slow_when_overloaded_and_retained_slots_stay_busy(self):
        arrivals = [
            Arrival("long", 0, 0, 1, tool_gap_seconds=10),
            Arrival("waiting", 1, 0, 1),
            Arrival("rejected", 2, 0, 1),
        ]
        report = replay_serving(arrivals, n=1, model_capacity=4, queue_limit=1, decode_tokens_per_second=1)
        self.assertEqual(report["arrivals"], 3)
        self.assertEqual(report["rejected"], 1)
        self.assertEqual(report["records"]["rejected"]["arrival_at"], 2)
        # At tool return the first generated token is part of the uncached
        # prompt: 1/100 s prefill + 1 s decode after the 10 s tool gap.
        self.assertEqual(report["records"]["long"]["model_stages"][1]["prefill_tokens"], 1)
        self.assertEqual(report["records"]["long"]["completed_at"], 12.01)
        self.assertEqual(report["records"]["waiting"]["admitted_at"], 12.01)
        idle = next(e for e in report["trace"] if e["event"] == "tool_idle")
        self.assertEqual(idle["retained_patch_slots"], 1)
        self.assertEqual(report["queue_seconds"]["0.95"], 11.01)

    def test_warm_cache_does_not_remove_tool_gap_or_eviction(self):
        arrivals = [
            Arrival("first", 0, 100, 10, prefix_identity="prefix-a"),
            Arrival("warm", 3, 100, 10, prefix_identity="prefix-a"),
            Arrival("other", 5, 100, 10, prefix_identity="prefix-b"),
            Arrival("cold", 8, 100, 10, prefix_identity="prefix-a"),
        ]
        report = replay_serving(arrivals, n=2, cache_capacity_tokens=100)
        self.assertTrue(report["records"]["warm"]["model_stages"][0]["warm"])
        self.assertFalse(report["records"]["cold"]["model_stages"][0]["warm"])
        self.assertTrue(any(e["event"] == "cache_evict" for e in report["trace"]))
        self.assertEqual(report["completed"], 4)
