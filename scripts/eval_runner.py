"""AI Agent Evaluation Runner for Managed Repositories.

Evaluates coding agent capability, negative constraint adherence, blast radius limits,
and qualitative code quality via LLM-as-a-Judge (G-Eval) against real-world tasks
stored in `evals/tasks.jsonl`.

Features:
- Deterministic checks: verification test command, forbidden paths, required invariants, max files touched.
- LLM-as-a-Judge: multi-dimensional rubric scoring (faithfulness, task completion, constraints, code quality).
- Statistical analysis: 95% Wilson Score confidence intervals, p50/p90/p95 latency percentiles.
- Regression detection: A/B comparison against baseline runs with --fail-on-regression CI gates.
- PR Scorecards: Generates rich GitHub-flavored Markdown tables for CI/CD pull request summaries.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from scripts.judge import JudgeResult, LLMJudge
except ImportError:
    try:
        from judge import JudgeResult, LLMJudge
    except ImportError:
        LLMJudge = None  # type: ignore
        JudgeResult = None  # type: ignore


@dataclass
class EvalTask:
    id: str
    prompt: str
    target_test: str
    task_type: str = "functional_bugfix"
    commit: str | None = None
    forbidden_paths: list[str] = field(default_factory=list)
    max_files_modified: int | None = None
    required_strings: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)
    max_turns: int = 5
    expected_output: str | None = None
    rubric: str | None = None
    tags: list[str] = field(default_factory=list)
    judge_model: str | None = None


@dataclass
class TaskResult:
    task: EvalTask
    passed: bool
    duration_s: float
    turns: int
    test_passed: bool
    violations: list[str] = field(default_factory=list)
    notes: str = ""
    judge_result: Optional[Any] = None  # JudgeResult
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "task_id": self.task.id,
            "task_type": self.task.task_type,
            "passed": self.passed,
            "duration_s": self.duration_s,
            "turns": self.turns,
            "test_passed": self.test_passed,
            "violations": self.violations,
            "notes": self.notes,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
        }
        if self.judge_result:
            data["judge"] = self.judge_result.to_dict() if hasattr(self.judge_result, "to_dict") else self.judge_result
        return data


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> Tuple[float, float, float]:
    """
    Calculates the Wilson score confidence interval for a binomial proportion.
    Standard in production ML evals to quantify uncertainty in small/medium task suites.
    Returns: (center_estimate_pct, lower_bound_pct, upper_bound_pct)
    """
    if total == 0:
        return 0.0, 0.0, 0.0

    # z-value for confidence level (default 95% -> 1.96)
    z = 1.95996 if confidence == 0.95 else 1.64485
    p_hat = successes / total

    denominator = 1 + (z**2 / total)
    center = (p_hat + (z**2 / (2 * total))) / denominator
    spread = z * math.sqrt((p_hat * (1 - p_hat) / total) + (z**2 / (4 * total**2))) / denominator

    lower = max(0.0, (center - spread)) * 100
    upper = min(1.0, (center + spread)) * 100
    estimate = p_hat * 100

    return round(estimate, 1), round(lower, 1), round(upper, 1)


def calculate_percentiles(values: List[float], percentiles_list: List[int]) -> Dict[str, float]:
    """Calculates p50, p90, p95, p99 percentiles."""
    if not values:
        return {f"p{p}": 0.0 for p in percentiles_list}
    sorted_v = sorted(values)
    res = {}
    for p in percentiles_list:
        idx = max(0, min(len(sorted_v) - 1, math.floor((p / 100.0) * len(sorted_v))))
        res[f"p{p}"] = round(sorted_v[idx], 2)
    return res


def load_tasks(tasks_file: Path) -> list[EvalTask]:
    if not tasks_file.is_file():
        return []
    tasks: list[EvalTask] = []
    with open(tasks_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
                tasks.append(
                    EvalTask(
                        id=data.get("id", f"task-{line_num}"),
                        prompt=data["prompt"],
                        target_test=data.get("target_test", "python scripts/verify.py"),
                        task_type=data.get("type", "functional_bugfix"),
                        commit=data.get("commit"),
                        forbidden_paths=data.get("forbidden_paths", []),
                        max_files_modified=data.get("max_files_modified"),
                        required_strings=data.get("required_strings", []),
                        target_files=data.get("target_files", []),
                        max_turns=data.get("max_turns", 5),
                        expected_output=data.get("expected_output"),
                        rubric=data.get("rubric"),
                        tags=data.get("tags", []),
                        judge_model=data.get("judge_model"),
                    )
                )
            except Exception as e:
                print(f"[WARN] Skipping invalid line {line_num} in {tasks_file}: {e}", file=sys.stderr)
    return tasks


def get_git_modified_files(repo_path: Path) -> set[str]:
    """Return set of modified/staged/untracked files relative to repo root."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        files = set()
        for line in proc.stdout.splitlines():
            if len(line) > 3:
                files.add(line[3:].strip())
        return files
    except Exception:
        return set()


def get_git_diff(repo_path: Path) -> str:
    """Returns the git diff (staged and unstaged) in the repo."""
    try:
        proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if proc.stdout.strip():
            return proc.stdout
        # Fallback to unstaged diff
        proc_unstaged = subprocess.run(
            ["git", "diff"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        return proc_unstaged.stdout
    except Exception:
        return ""


def check_forbidden_paths(modified_files: list[str], forbidden_patterns: list[str]) -> list[str]:
    violations = []
    for f in modified_files:
        norm_f = f.replace("\\", "/")
        for pat in forbidden_patterns:
            norm_pat = pat.replace("\\", "/")
            if fnmatch.fnmatch(norm_f, norm_pat) or norm_f.startswith(norm_pat.rstrip("*")):
                violations.append(f"Modified forbidden path: '{norm_f}' matches pattern '{pat}'")
    return violations


def check_required_strings(repo_path: Path, target_files: list[str], required_strings: list[str]) -> list[str]:
    violations = []
    for req in required_strings:
        found = False
        files_to_check = target_files if target_files else get_git_modified_files(repo_path)
        for rel in files_to_check:
            p = repo_path / rel
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    if req in content:
                        found = True
                        break
                except Exception:
                    pass
        if not found:
            violations.append(f"Required string/invariant not found: '{req}'")
    return violations


def run_single_eval(
    task: EvalTask,
    repo_path: Path,
    agent_cmd: str | None = None,
    dry_run: bool = False,
    judge: Optional[Any] = None,
) -> TaskResult:
    start_time = time.time()
    violations: list[str] = []

    print(f"\n▶ Running Eval Task: [{task.id}] ({task.task_type})")
    print(f"  Prompt: {task.prompt}")

    if dry_run:
        print("  [DRY-RUN] Simulating task execution without calling live agent API...")
        duration = time.time() - start_time
        judge_res = None
        if judge:
            judge_res = judge.evaluate_heuristic(
                task_id=task.id,
                prompt=task.prompt,
                git_diff="(simulated dry run diff: +def fix(): pass)",
                test_passed=True,
                violations=[],
                expected_output=task.expected_output,
            )
        return TaskResult(
            task=task,
            passed=True,
            duration_s=round(duration, 2),
            turns=1,
            test_passed=True,
            violations=[],
            notes="Dry-run simulated pass",
            judge_result=judge_res,
        )

    initial_files = get_git_modified_files(repo_path)

    # If an agent command is provided, invoke it
    turns = 1
    if agent_cmd:
        full_agent_cmd = f"{agent_cmd} \"{task.prompt}\""
        print(f"  • Invoking Agent: {full_agent_cmd}")
        try:
            subprocess.run(
                full_agent_cmd,
                cwd=repo_path,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            violations.append("Agent execution timed out (exceeded 180s)")
        except subprocess.CalledProcessError as e:
            violations.append(f"Agent execution exited with error code {e.returncode}")

    # Inspect git changes: compute delta if agent ran, otherwise check current
    current_files = get_git_modified_files(repo_path)
    modified_files = list(current_files - initial_files) if agent_cmd else []
    git_diff = get_git_diff(repo_path)

    # 1. Check Blast Radius
    if task.max_files_modified is not None and len(modified_files) > task.max_files_modified:
        violations.append(
            f"Blast radius exceeded: {len(modified_files)} files modified (limit: {task.max_files_modified})"
        )

    # 2. Check Forbidden Paths (Negative Constraints)
    if task.forbidden_paths:
        violations.extend(check_forbidden_paths(modified_files, task.forbidden_paths))

    # 3. Check Required Strings / Design Invariants
    if task.required_strings:
        violations.extend(check_required_strings(repo_path, task.target_files, task.required_strings))

    # 4. Check Target Test (Functional Correctness)
    test_passed = False
    if task.target_test:
        print(f"  • Running Verification Check: {task.target_test}")
        test_proc = subprocess.run(
            task.target_test,
            cwd=repo_path,
            shell=True,
            capture_output=True,
            text=True,
        )
        test_passed = (test_proc.returncode == 0)
        if not test_passed:
            sample_err = (test_proc.stderr or test_proc.stdout)[-300:].strip()
            violations.append(f"Verification test failed ({task.target_test}): {sample_err}")
    else:
        test_passed = True

    # 5. LLM-as-a-Judge Evaluation (if enabled)
    judge_res = None
    if judge:
        print(f"  • Running Judge Evaluation ({judge.model})...")
        judge_res = judge.evaluate(
            task_id=task.id,
            prompt=task.prompt,
            git_diff=git_diff,
            test_passed=test_passed,
            violations=violations,
            expected_output=task.expected_output,
            custom_rubric=task.rubric,
        )
        print(f"    - Score: {judge_res.composite_score}/5.0 (Verdict: {judge_res.verdict})")
        print(f"    - Reason: {judge_res.reasoning}")

    duration = time.time() - start_time
    deterministic_passed = test_passed and len(violations) == 0
    judge_passed = (judge_res.verdict == "PASS") if judge_res else True
    overall_passed = deterministic_passed and judge_passed

    if overall_passed:
        print(f"  ✔ PASSED in {duration:.1f}s")
    else:
        print(f"  ❌ FAILED ({len(violations)} violation(s))")
        for v in violations:
            print(f"     - {v}")

    return TaskResult(
        task=task,
        passed=overall_passed,
        duration_s=round(duration, 2),
        turns=turns,
        test_passed=test_passed,
        violations=violations,
        judge_result=judge_res,
    )


@dataclass
class EvalComparison:
    """A/B Regression comparison between baseline run and current run."""

    baseline_pass_rate: float
    current_pass_rate: float
    pass_rate_delta: float
    improvements: List[str]  # Tasks that failed in baseline but passed now
    regressions: List[str]   # Tasks that passed in baseline but failed now (CRITICAL)
    unchanged_passed: List[str]
    unchanged_failed: List[str]
    p50_latency_delta_s: float
    avg_score_delta: float


def compare_runs(baseline: Dict[str, Any], current_results: List[TaskResult]) -> EvalComparison:
    """Compares current results against historical baseline dict."""
    base_tasks: Dict[str, bool] = {
        r.get("task_id", ""): r.get("passed", False)
        for r in baseline.get("results", [])
    }
    base_total = len(base_tasks)
    base_passed = sum(1 for v in base_tasks.values() if v)
    base_summary_rate = baseline.get("summary", {}).get("pass_rate_pct")
    base_rate = float(base_summary_rate) if base_summary_rate is not None else ((base_passed / base_total * 100) if base_total > 0 else 0.0)

    curr_total = len(current_results)
    curr_passed = sum(1 for r in current_results if r.passed)
    curr_rate = (curr_passed / curr_total * 100) if curr_total > 0 else 0.0

    improvements: List[str] = []
    regressions: List[str] = []
    unchanged_passed: List[str] = []
    unchanged_failed: List[str] = []

    for r in current_results:
        tid = r.task.id
        was_passed = base_tasks.get(tid)
        is_passed = r.passed
        if was_passed is None:
            continue
        if not was_passed and is_passed:
            improvements.append(tid)
        elif was_passed and not is_passed:
            regressions.append(tid)
        elif was_passed and is_passed:
            unchanged_passed.append(tid)
        else:
            unchanged_failed.append(tid)

    # Latency comparison
    base_p50 = baseline.get("summary", {}).get("latency_percentiles", {}).get("p50", 0.0)
    curr_p50 = calculate_percentiles([r.duration_s for r in current_results], [50]).get("p50", 0.0)

    # Score comparison
    base_score = baseline.get("summary", {}).get("avg_judge_score", 0.0)
    judge_scores = [r.judge_result.composite_score for r in current_results if r.judge_result]
    curr_score = (sum(judge_scores) / len(judge_scores)) if judge_scores else 0.0

    return EvalComparison(
        baseline_pass_rate=round(base_rate, 1),
        current_pass_rate=round(curr_rate, 1),
        pass_rate_delta=round(curr_rate - base_rate, 1),
        improvements=improvements,
        regressions=regressions,
        unchanged_passed=unchanged_passed,
        unchanged_failed=unchanged_failed,
        p50_latency_delta_s=round(curr_p50 - base_p50, 2),
        avg_score_delta=round(curr_score - base_score, 2),
    )


def generate_markdown_scorecard(
    repo_name: str,
    results: List[TaskResult],
    comparison: Optional[EvalComparison] = None,
) -> str:
    """Generates an executive-level GitHub Flavored Markdown scorecard table."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    rate, lower, upper = wilson_score_interval(passed, total)
    durations = [r.duration_s for r in results]
    percentiles_dict = calculate_percentiles(durations, [50, 95])

    judge_scores = [r.judge_result.composite_score for r in results if r.judge_result]
    avg_judge = round(sum(judge_scores) / len(judge_scores), 2) if judge_scores else None

    lines = [
        f"## 📊 AI Agent Evaluation Scorecard: `{repo_name}`",
        "",
        "### Operational & Capability Overview",
        "",
        "| Metric | Result | Benchmark / Notes |",
        "| :--- | :--- | :--- |",
        f"| **Pass Rate** | **{passed}/{total} ({rate}%)** | 95% Wilson CI: `[{lower}% - {upper}%]` |",
        f"| **p50 Latency** | `{percentiles_dict.get('p50', 0.0)}s` | Median task completion time |",
        f"| **p95 Latency** | `{percentiles_dict.get('p95', 0.0)}s` | Tail latency threshold |",
    ]

    if avg_judge is not None:
        lines.append(f"| **Judge Quality Score** | **{avg_judge} / 5.0** | Weighted G-Eval rubric |")

    if comparison:
        lines.extend([
            "",
            "### 🔄 A/B Regression Delta (vs Baseline)",
            "",
            "| Comparison Dimension | Baseline | Current | Delta | Status |",
            "| :--- | :--- | :--- | :--- | :--- |",
            f"| **Pass Rate** | {comparison.baseline_pass_rate}% | {comparison.current_pass_rate}% | {comparison.pass_rate_delta:+} | {'🟢 Improvement' if comparison.pass_rate_delta >= 0 else '🔴 Regression'} |",
            f"| **p50 Latency** | Baseline | Current | {comparison.p50_latency_delta_s:+}s | {'🟢 Faster' if comparison.p50_latency_delta_s <= 0 else '🟡 Slower'} |",
            f"| **Regressions (Critical)** | - | - | **{len(comparison.regressions)}** | {'✅ None' if not comparison.regressions else f'🚨 {len(comparison.regressions)} Task(s) Regressed'} |",
        ])

    lines.extend([
        "",
        "### Detailed Task Matrix",
        "",
        "| Status | Task ID | Type | Duration | Judge Score | Violations / Reasoning |",
        "| :---: | :--- | :--- | :---: | :---: | :--- |",
    ])

    for r in results:
        status_badge = "🟢 `PASS`" if r.passed else "🔴 `FAIL`"
        score_str = f"{r.judge_result.composite_score}/5.0" if r.judge_result else "N/A"
        diag = "; ".join(r.violations) if r.violations else (r.judge_result.reasoning if r.judge_result else "All checks passed")
        diag_clean = diag.replace("|", "\\|")[:90]
        lines.append(f"| {status_badge} | `{r.task.id}` | {r.task.task_type} | {r.duration_s}s | {score_str} | {diag_clean} |")

    lines.append("")
    return "\n".join(lines)


def run_repo_evals(
    repo_path: Path,
    suite: str = "full",
    agent_cmd: str | None = None,
    dry_run: bool = False,
    enable_judge: bool = False,
    judge_model: str = "gpt-4o-mini",
    baseline_path: Optional[Path] = None,
    output_json: Optional[Path] = None,
    output_scorecard: Optional[Path] = None,
    fail_on_regression: bool = False,
) -> tuple[int, int]:
    """
    Run evaluation suite for a single repository.
    Returns: (passed_count, total_count)
    """
    tasks_file = repo_path / "evals" / "tasks.jsonl"
    if not tasks_file.is_file():
        print(f"[SKIP] {repo_path.name}: No evals/tasks.jsonl found.")
        return (0, 0)

    tasks = load_tasks(tasks_file)
    if not tasks:
        print(f"[SKIP] {repo_path.name}: evals/tasks.jsonl is empty.")
        return (0, 0)

    if suite == "smoke":
        tasks = tasks[:1]

    # Initialize Judge if requested
    judge = None
    if enable_judge and LLMJudge is not None:
        judge = LLMJudge(model=judge_model)
        print(f"⚖️ LLM-as-a-Judge initialized with model: {judge_model}")

    print(f"\n========================================================")
    print(f"🚀 RUNNING INDUSTRIAL EVALUATION: {repo_path.name} ({len(tasks)} task(s))")
    print(f"========================================================")

    results: list[TaskResult] = []
    for task in tasks:
        results.append(run_single_eval(task, repo_path, agent_cmd, dry_run, judge=judge))

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    rate, lower, upper = wilson_score_interval(passed, total)

    # Baseline comparison
    comparison = None
    if baseline_path and baseline_path.is_file():
        try:
            base_data = json.loads(baseline_path.read_text(encoding="utf-8"))
            comparison = compare_runs(base_data, results)
        except Exception as e:
            print(f"[WARN] Could not load baseline {baseline_path}: {e}", file=sys.stderr)

    scorecard_md = generate_markdown_scorecard(repo_path.name, results, comparison)
    print(f"\n{scorecard_md}")

    # Export outputs if requested
    if output_scorecard:
        output_scorecard.parent.mkdir(parents=True, exist_ok=True)
        output_scorecard.write_text(scorecard_md, encoding="utf-8")
        print(f"💾 Markdown scorecard written to: {output_scorecard}")

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        durations = [r.duration_s for r in results]
        percentiles_dict = calculate_percentiles(durations, [50, 90, 95])
        export_payload = {
            "repo": repo_path.name,
            "timestamp": time.time(),
            "summary": {
                "total": total,
                "passed": passed,
                "pass_rate_pct": rate,
                "wilson_ci_95": {"lower": lower, "upper": upper},
                "latency_percentiles": percentiles_dict,
            },
            "results": [r.to_dict() for r in results],
        }
        output_json.write_text(json.dumps(export_payload, indent=2), encoding="utf-8")
        print(f"💾 JSON results written to: {output_json}")

    # Check regression policy
    if fail_on_regression and comparison and comparison.regressions:
        print(f"🚨 CRITICAL REGRESSION: {len(comparison.regressions)} task(s) regressed from baseline!", file=sys.stderr)
        return (0, total)

    return passed, total


def main() -> int:
    parser = argparse.ArgumentParser(description="Industrial AI Agent Evaluation Runner")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Target repo to evaluate")
    parser.add_argument("--suite", choices=["smoke", "full"], default="full", help="Evaluation suite depth")
    parser.add_argument("--agent", default=None, help="Agent CLI command (e.g. 'claude -p' or 'opencode')")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without calling live agent")
    parser.add_argument("--judge", action="store_true", help="Enable LLM-as-a-Judge rubric scoring")
    parser.add_argument("--judge-model", default="gpt-4o-mini", help="Model used for judge evaluations")
    parser.add_argument("--baseline", type=Path, default=None, help="Baseline JSON report to compare against")
    parser.add_argument("--output-json", type=Path, default=None, help="Path to export JSON evaluation report")
    parser.add_argument("--output-scorecard", type=Path, default=None, help="Path to export Markdown PR scorecard")
    parser.add_argument("--fail-on-regression", action="store_true", help="Exit code 1 if any task regressed")
    args = parser.parse_args()

    repo = args.repo.resolve()
    passed, total = run_repo_evals(
        repo,
        suite=args.suite,
        agent_cmd=args.agent,
        dry_run=args.dry_run,
        enable_judge=args.judge,
        judge_model=args.judge_model,
        baseline_path=args.baseline,
        output_json=args.output_json,
        output_scorecard=args.output_scorecard,
        fail_on_regression=args.fail_on_regression,
    )

    if total == 0:
        return 0
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
