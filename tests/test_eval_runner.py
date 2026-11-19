"""
Unit and integration tests for Industrial AI Agent Evaluation Runner (eval_runner.py)
and LLM-as-a-Judge (judge.py).
"""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_runner import (
    EvalTask,
    TaskResult,
    calculate_percentiles,
    compare_runs,
    generate_markdown_scorecard,
    load_tasks,
    run_repo_evals,
    run_single_eval,
    wilson_score_interval,
)
from scripts.judge import JudgeResult, LLMJudge


class TestEvaluationStatistics(unittest.TestCase):
    def test_wilson_score_interval_bounds(self):
        # 0 total
        est, low, up = wilson_score_interval(0, 0)
        self.assertEqual((est, low, up), (0.0, 0.0, 0.0))

        # 10 out of 10 successes
        est, low, up = wilson_score_interval(10, 10)
        self.assertEqual(est, 100.0)
        self.assertGreater(low, 65.0)  # Lower bound around 72%
        self.assertEqual(up, 100.0)

        # 8 out of 10
        est, low, up = wilson_score_interval(8, 10)
        self.assertEqual(est, 80.0)
        self.assertLess(low, 80.0)
        self.assertGreater(up, 80.0)

        # 50 out of 100
        est, low, up = wilson_score_interval(50, 100)
        self.assertEqual(est, 50.0)
        self.assertAlmostEqual(low, 40.4, places=1)
        self.assertAlmostEqual(up, 59.6, places=1)

    def test_calculate_percentiles(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        res = calculate_percentiles(values, [50, 95])
        self.assertEqual(res["p50"], 6.0)
        self.assertEqual(res["p95"], 10.0)

        empty_res = calculate_percentiles([], [50, 95])
        self.assertEqual(empty_res["p50"], 0.0)


class TestLLMJudge(unittest.TestCase):
    def setUp(self):
        self.judge = LLMJudge(model="gpt-4o-mini", api_key=None)  # Uses heuristic fallback

    def test_heuristic_judge_passing_run(self):
        res = self.judge.evaluate_heuristic(
            task_id="task-01",
            prompt="Refactor connection retry loop in database.py",
            git_diff="""
diff --git a/database.py b/database.py
--- a/database.py
+++ b/database.py
@@ -10,3 +10,6 @@
+def retry_connection():
+    for _ in range(3):
+        connect()
""",
            test_passed=True,
            violations=[],
        )
        self.assertEqual(res.verdict, "PASS")
        self.assertGreaterEqual(res.composite_score, 4.0)
        self.assertIn("faithfulness", res.scores)
        self.assertIn("task_completion", res.scores)

    def test_heuristic_judge_failing_run(self):
        res = self.judge.evaluate_heuristic(
            task_id="task-02",
            prompt="Fix token auth bug",
            git_diff="",
            test_passed=False,
            violations=["Verification test failed"],
        )
        self.assertEqual(res.verdict, "FAIL")
        self.assertLess(res.composite_score, 4.0)
        self.assertIn("Functional tests failed", res.reasoning)


class TestEvalComparisonAndScorecard(unittest.TestCase):
    def test_compare_runs_detects_regressions_and_improvements(self):
        baseline = {
            "summary": {"pass_rate_pct": 50.0, "latency_percentiles": {"p50": 5.0}},
            "results": [
                {"task_id": "t1", "passed": True},
                {"task_id": "t2", "passed": False},
                {"task_id": "t3", "passed": True},
            ],
        }

        task1 = EvalTask(id="t1", prompt="t1", target_test="")
        task2 = EvalTask(id="t2", prompt="t2", target_test="")
        task3 = EvalTask(id="t3", prompt="t3", target_test="")

        current_results = [
            TaskResult(task=task1, passed=True, duration_s=4.0, turns=1, test_passed=True),   # Unchanged passed
            TaskResult(task=task2, passed=True, duration_s=4.0, turns=1, test_passed=True),   # Improvement (F -> P)
            TaskResult(task=task3, passed=False, duration_s=4.0, turns=1, test_passed=False), # Regression (P -> F)
        ]

        comp = compare_runs(baseline, current_results)
        self.assertEqual(comp.improvements, ["t2"])
        self.assertEqual(comp.regressions, ["t3"])
        self.assertEqual(comp.unchanged_passed, ["t1"])
        self.assertEqual(comp.pass_rate_delta, 16.7)  # 66.7% vs 50.0%

    def test_generate_markdown_scorecard(self):
        task1 = EvalTask(id="task-01", prompt="Fix bug", target_test="", task_type="bugfix")
        res1 = TaskResult(
            task=task1,
            passed=True,
            duration_s=2.5,
            turns=1,
            test_passed=True,
            judge_result=JudgeResult(
                task_id="task-01",
                verdict="PASS",
                composite_score=4.8,
                scores={"faithfulness": 5.0, "task_completion": 5.0, "constraint_adherence": 5.0, "code_quality": 4.5},
                reasoning="Clean solution with passing tests.",
                model="gpt-4o-mini",
            ),
        )

        md = generate_markdown_scorecard("my-repo", [res1])
        self.assertIn("## 📊 AI Agent Evaluation Scorecard: `my-repo`", md)
        self.assertIn("95% Wilson CI", md)
        self.assertIn("4.8 / 5.0", md)
        self.assertIn("🟢 `PASS`", md)
        self.assertIn("`task-01`", md)


class TestEndToEndEvalRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "evals").mkdir(parents=True)
        (self.repo / "scripts").mkdir(parents=True)

        # Mock tasks.jsonl
        tasks = [
            {"id": "test-task-1", "type": "functional_bugfix", "prompt": "Fix calculation in calc.py", "target_test": ""},
            {"id": "test-task-2", "type": "constraint_compliance", "prompt": "Add helper function", "target_test": "", "forbidden_paths": ["forbidden/**"]},
        ]
        with open(self.repo / "evals" / "tasks.jsonl", "w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_repo_evals_dry_run_with_judge_and_exports(self):
        out_json = self.repo / "report.json"
        out_md = self.repo / "scorecard.md"

        passed, total = run_repo_evals(
            self.repo,
            suite="full",
            dry_run=True,
            enable_judge=True,
            judge_model="gpt-4o-mini",
            output_json=out_json,
            output_scorecard=out_md,
        )

        self.assertEqual(total, 2)
        self.assertEqual(passed, 2)
        self.assertTrue(out_json.is_file())
        self.assertTrue(out_md.is_file())

        json_data = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertEqual(json_data["summary"]["total"], 2)
        self.assertEqual(json_data["summary"]["passed"], 2)
        self.assertIn("wilson_ci_95", json_data["summary"])
        self.assertEqual(len(json_data["results"]), 2)
        self.assertIn("judge", json_data["results"][0])


if __name__ == "__main__":
    unittest.main()
