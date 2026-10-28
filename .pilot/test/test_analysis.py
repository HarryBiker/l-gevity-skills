"""Parser tests for .pilot/pilot_analysis.py and the result redactor.

    python -m unittest discover -s .pilot/test -v

The synthetic-*.jsonl streams are hand-written. They prove that the parser
extracts the acceptance facts from the event shapes they contain; they are not
recorded runs and prove nothing about the methodology. The codex stream uses
assumed collab_tool_call field names; a real run's result JSON lists the
field names it actually produced under stream.collab_item_keys.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import pilot_analysis  # noqa: E402
import run_pilot  # noqa: E402


def facts(name: str, runtime: str = "claude") -> dict:
    return pilot_analysis.analyze(pilot_analysis.load_stream(HERE / name), runtime)


class ClaudeForegroundStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = facts("synthetic-claude-multi.jsonl")
        cls.acceptance = cls.analysis["acceptance"]

    def test_launches_in_order_with_types_and_times(self):
        launches = self.acceptance["agent_launches"]
        self.assertEqual([launch["tool_use_id"] for launch in launches], ["tu_a1", "tu_a2", "tu_a3", "tu_a4", "tu_a5"])
        self.assertEqual(launches[3]["subagent_type"], "alchemy-analyst")
        self.assertEqual((launches[1]["launched_at"], launches[1]["finished_at"]), (9.0, 22.0))
        self.assertEqual(self.acceptance["agent_launch_count"], 4)

    def test_parallel_overlap(self):
        self.assertIs(self.acceptance["parallel_overlap"], True)

    def test_review_after_implementation_and_correction(self):
        self.assertTrue(self.acceptance["review_after_implementation"])
        self.assertEqual(self.acceptance["review_launches"], ["tu_a4"])
        self.assertTrue(self.acceptance["correction_after_review"])
        self.assertEqual(self.acceptance["correction_launches"], ["tu_a5"])

    def test_skills_by_lead_and_subagent(self):
        self.assertEqual(self.acceptance["skills_loaded_by_lead"], ["alchemy", "alchemy-orchestrate"])
        by_agent = self.acceptance["skills_loaded_by_subagents"]
        self.assertEqual(by_agent["tu_a2"], ["alchemy-orchestrate", "test-strategy"])
        self.assertEqual(by_agent["tu_a3"], ["architecture-guidelines"])
        self.assertEqual(by_agent["tu_a4"], ["test-strategy"])

    def test_execution_and_dispatch_lines(self):
        self.assertEqual(self.acceptance["execution_mode"], "multi-agent")
        self.assertTrue(self.acceptance["execution_line"].startswith("multi-agent"))
        self.assertEqual(self.acceptance["dispatch"], "ADAPTIVE")

    def test_orchestration_checks_with_exit_status(self):
        checks = [(check["kind"], check["exit_status"], check["verdict"]) for check in self.acceptance["orchestration_checks"]]
        self.assertEqual(checks, [("plan", 0, "PASS"), ("handoff", 1, "REJECT"), ("gate", 0, "PASS")])

    def test_injected_failure_and_retry(self):
        injected = self.acceptance["injected_failure"]
        self.assertEqual(injected["blocked_launches"], 1)
        self.assertTrue(injected["retried"])
        self.assertTrue(injected["retry_same_subagent_type"])
        self.assertTrue(self.acceptance["agent_launches"][0]["blocked"])

    def test_metrics_from_result_event(self):
        metrics = self.analysis["metrics"]
        self.assertEqual(metrics["total_cost_usd"], 1.23)
        self.assertEqual(metrics["num_turns"], 12)
        self.assertEqual(metrics["usage"]["cache_read_input_tokens"], 30)
        self.assertEqual(self.analysis["init"]["model"], "synthetic-model")


class ClaudeBackgroundStream(unittest.TestCase):
    def test_background_agents_finish_at_their_notification(self):
        acceptance = facts("synthetic-claude-background.jsonl")["acceptance"]
        first, second, review = acceptance["agent_launches"]
        self.assertTrue(first["background"] and second["background"])
        self.assertEqual((first["finished_at"], second["finished_at"]), (10.0, 12.0))
        self.assertIs(acceptance["parallel_overlap"], True)
        self.assertTrue(acceptance["review_after_implementation"])
        self.assertFalse(acceptance["correction_after_review"])
        self.assertEqual(acceptance["execution_mode"], "multi-agent")


class ClaudeSingleAgentStream(unittest.TestCase):
    def test_no_launches_means_no_overlap(self):
        stream = [
            (0.0, {"type": "system", "subtype": "init", "model": "m"}),
            (1.0, {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
                {"type": "text", "text": "Dispatch:   DIRECT\nExecution:  single-agent — one file"},
                {"type": "tool_use", "id": "t1", "name": "Edit", "input": {}},
            ]}}),
            (2.0, {"type": "result", "subtype": "success", "is_error": False, "num_turns": 2}),
        ]
        acceptance = pilot_analysis.analyze_claude(stream)["acceptance"]
        self.assertEqual(acceptance["agent_launches"], [])
        self.assertIs(acceptance["parallel_overlap"], False)
        self.assertFalse(acceptance["review_after_implementation"])
        self.assertEqual(acceptance["skills_loaded_by_subagents"], {})
        self.assertEqual((acceptance["execution_mode"], acceptance["dispatch"]), ("single-agent", "DIRECT"))


class CodexStream(unittest.TestCase):
    def test_spawn_wait_and_usage(self):
        analysis = facts("synthetic-codex-multi.jsonl", "codex")
        acceptance = analysis["acceptance"]
        self.assertEqual(acceptance["agent_launch_count"], 3)
        self.assertEqual([launch["role"] for launch in acceptance["agent_launches"]], ["implementer", "implementer", "analyst"])
        self.assertIs(acceptance["parallel_overlap"], True)
        self.assertTrue(acceptance["review_after_implementation"])
        self.assertEqual(acceptance["skills_loaded_by_lead"], ["alchemy-orchestrate"])
        self.assertIsNone(acceptance["skills_loaded_by_subagents"])
        self.assertEqual([(c["kind"], c["exit_status"], c["verdict"]) for c in acceptance["orchestration_checks"]], [("plan", 0, "PASS")])
        self.assertEqual(analysis["metrics"]["usage"], {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 20, "reasoning_output_tokens": 5})
        self.assertIn("receiver_thread_ids", analysis["collab_item_keys"])


class Redaction(unittest.TestCase):
    def test_paths_home_and_tokens_are_redacted(self):
        project = Path(run_pilot.tempfile.gettempdir()) / "alchemy-pilot-x"
        redact = run_pilot.make_redactor(project)
        record = redact({
            "a": f"cd {project} && ls",
            "b": [f"{project.as_posix()}/src/app.js", str(Path.home() / "secrets.txt")],
            "c": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123",
            "d": "key sk-ant-api03-ABCDEFGHIJKLMNOP",
        })
        text = repr(record)
        self.assertNotIn(str(Path.home()), text)
        self.assertNotIn(Path.home().as_posix(), text)
        self.assertIn("<run-project>", record["a"])
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123", text)
        self.assertNotIn("sk-ant-api03", text)


if __name__ == "__main__":
    unittest.main()
