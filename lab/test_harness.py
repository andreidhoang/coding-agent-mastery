"""Independent contract cases for the educational fixture, not a training reward suite."""
import json
from pathlib import Path
import tempfile
import unittest

from harness import Ledger, Tools, ScriptedModel, bounded, digest, dispatch, run, token_work


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.file = self.repo / "calculator.py"
        self.file.write_text("def add(a, b):\n    return a - b\n")
        self.db = self.root / "ledger.sqlite"
        self.ledger = Ledger(self.db)
        self.tools = Tools(self.repo)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def edit(self, call_id="edit", **changes):
        args = {"path": "calculator.py", "sha256": digest(self.file.read_bytes()),
                "old": "return a - b", "new": "return a + b"}
        args.update(changes)
        return {"id": call_id, "name": "edit", "args": args}

    def test_repair_changes_real_file_and_verifier_result(self):
        self.assertFalse(self.tools.execute("test", {})["passed"])
        status, _ = run(ScriptedModel(), self.tools, self.ledger)
        self.assertEqual(status, "verified")
        self.assertIn("return a + b", self.file.read_text())
        self.assertEqual(len([e for e in self.ledger.events() if e["kind"] == "tool_result"]), 3)

    def test_replayed_completed_action_does_not_apply_again(self):
        call = self.edit()
        result = dispatch(call, self.tools, self.ledger)
        self.assertTrue(result["ok"])
        self.assertEqual(dispatch(call, self.tools, self.ledger), result)
        self.assertEqual(len([e for e in self.ledger.events() if e["kind"] == "tool_result"]), 1)

    def test_reused_id_with_changed_arguments_is_rejected(self):
        dispatch(self.edit(), self.tools, self.ledger)
        with self.assertRaisesRegex(ValueError, "collision"):
            dispatch(self.edit(new="return 0"), self.tools, self.ledger)

    def test_stale_read_cannot_overwrite_new_content(self):
        call = self.edit()
        self.file.write_text("# human edit\n" + self.file.read_text())
        result = dispatch(call, self.tools, self.ledger)
        self.assertEqual(result["detail"], "stale_read")
        self.assertTrue(self.file.read_text().startswith("# human edit"))

    def test_duplicate_anchor_is_rejected(self):
        self.file.write_text("return a - b\nreturn a - b\n")
        result = dispatch(self.edit(), self.tools, self.ledger)
        self.assertEqual(result["detail"], "edit_anchor_must_be_unique")

    def test_traversal_and_symlink_escape_are_denied(self):
        outside = self.root / "calculator.py"
        outside.write_text("outside")
        self.file.unlink()
        self.file.symlink_to(outside)
        for i, path in enumerate(["../calculator.py", "calculator.py"]):
            result = dispatch({"id": str(i), "name": "read", "args": {"path": path}}, self.tools, self.ledger)
            self.assertFalse(result["ok"])
            self.assertEqual(result["detail"], "path_denied")

    def test_denial_is_a_durable_observation(self):
        result = dispatch({"id": "x", "name": "shell", "args": {}}, self.tools, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(self.ledger.events()[-1]["payload"], result)

    def test_invalid_arguments_do_not_execute(self):
        result = dispatch({"id": "x", "name": "test", "args": {"command": "anything"}}, self.tools, self.ledger)
        self.assertEqual(result["detail"], "invalid_tool_schema")

    def test_crash_after_effect_is_unknown_and_never_replayed(self):
        call = self.edit()
        self.ledger.begin(call)
        self.tools.execute(call["name"], call["args"])
        # Simulate process loss before recording completion.
        self.ledger.close()
        self.ledger = Ledger(self.db)
        result = dispatch(call, self.tools, self.ledger)
        self.assertEqual(result["error"], "outcome_unknown")
        self.assertIn("return a + b", self.file.read_text())

    def test_asserting_done_does_not_mean_verified(self):
        class Done:
            def respond(self, history):
                return {"final": "All tests pass, trust me"}
        status, _ = run(Done(), self.tools, self.ledger)
        self.assertEqual(status, "unverified")

    def test_clean_exit_before_assertions_is_not_a_pass(self):
        self.file.write_text("import sys\nsys.exit(0)\n")
        result = self.tools.execute("test", {})
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["passed"])

    def test_replayed_test_cannot_verify_a_different_revision(self):
        self.file.write_text("def add(a,b):\n    return a + b\n")
        test_call = {"id": "old-test", "name": "test", "args": {}}
        self.assertTrue(dispatch(test_call, self.tools, self.ledger)["value"]["passed"])
        self.file.write_text("def add(a,b):\n    return a - b\n")
        class ReplayTest:
            def respond(self, history):
                if len(history) == 1:
                    return {"call": test_call}
                return {"final": "Done"}
        self.assertEqual(run(ReplayTest(), self.tools, self.ledger)[0], "unverified")
        self.assertFalse(self.tools.execute("test", {})["passed"])

    def test_loop_has_external_call_and_turn_budgets(self):
        class Repeat:
            def respond(self, history):
                return {"call": {"id": str(len(history)), "name": "read", "args": {"path": "calculator.py"}}}
        self.assertEqual(run(Repeat(), self.tools, self.ledger, max_calls=2)[0], "call_budget")
        self.assertEqual(run(Repeat(), self.tools, self.ledger, max_turns=1)[0], "turn_budget")

    def test_truncation_preserves_failure_tail_with_size_bound(self):
        output = bounded("start\n" + "x" * 9000 + "\nAssertionError: important")
        self.assertLessEqual(len(output), 1200)
        self.assertTrue(output.startswith("start"))
        self.assertTrue(output.endswith("AssertionError: important"))

    def test_cost_formula_matches_explicit_per_turn_sum(self):
        for prefix, delta, turns in [(0, 0, 1), (10, 0, 5), (3, 2, 4), (20_000, 3000, 100)]:
            v = token_work(prefix, delta, turns)
            self.assertEqual(v["uncached"], sum(prefix + t * delta for t in range(turns)))
            self.assertEqual(v["read"], sum(prefix + t * delta for t in range(turns - 1)))
            self.assertEqual(v["written"] + v["read"], v["uncached"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
