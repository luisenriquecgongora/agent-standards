"""AI Agent Evaluation Runner for Managed Repositories.

Evaluates coding agent capability, negative constraint adherence, and blast radius limits
against real-world tasks stored in `evals/tasks.jsonl`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


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


@dataclass
class TaskResult:
    task: EvalTask
    passed: bool
    duration_s: float
    turns: int
    test_passed: bool
    violations: list[str] = field(default_factory=list)
    notes: str = ""


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
                # Format is "XY filename"
                files.add(line[3:].strip())
        return files
    except Exception:
        return set()


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
) -> TaskResult:
    start_time = time.time()
    violations: list[str] = []

    print(f"\n▶ Running Eval Task: [{task.id}] ({task.task_type})")
    print(f"  Prompt: {task.prompt}")

    if dry_run:
        print("  [DRY-RUN] Simulating task execution without calling live agent API...")
        duration = time.time() - start_time
        return TaskResult(
            task=task,
            passed=True,
            duration_s=round(duration, 2),
            turns=1,
            test_passed=True,
            violations=[],
            notes="Dry-run simulated pass",
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

    duration = time.time() - start_time
    passed = test_passed and len(violations) == 0

    if passed:
        print(f"  ✔ PASSED in {duration:.1f}s")
    else:
        print(f"  ❌ FAILED ({len(violations)} violation(s))")
        for v in violations:
            print(f"     - {v}")

    return TaskResult(
        task=task,
        passed=passed,
        duration_s=round(duration, 2),
        turns=turns,
        test_passed=test_passed,
        violations=violations,
    )


def run_repo_evals(
    repo_path: Path,
    suite: str = "full",
    agent_cmd: str | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Run evaluation suite for a single repository. Returns (passed_count, total_count)."""
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

    print(f"\n========================================================")
    print(f"🚀 RUNNING EVALUATION: {repo_path.name} ({len(tasks)} task(s))")
    print(f"========================================================")

    results: list[TaskResult] = []
    for task in tasks:
        results.append(run_single_eval(task, repo_path, agent_cmd, dry_run))

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    score_pct = (passed / total) * 100 if total > 0 else 0

    print(f"\n--------------------------------------------------------")
    print(f"📊 {repo_path.name} SCORECARD: {passed}/{total} PASSED ({score_pct:.1f}%)")
    print(f"--------------------------------------------------------")
    for r in results:
        status_icon = "✔" if r.passed else "❌"
        print(f"  {status_icon} [{r.task.id}] {r.task.task_type} ({r.duration_s}s)")

    return passed, total


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Agent Evaluation Runner")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Target repo to evaluate")
    parser.add_argument("--suite", choices=["smoke", "full"], default="full", help="Evaluation suite depth")
    parser.add_argument("--agent", default=None, help="Agent CLI command (e.g. 'claude -p' or 'opencode')")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without calling live agent")
    args = parser.parse_args()

    repo = args.repo.resolve()
    passed, total = run_repo_evals(repo, suite=args.suite, agent_cmd=args.agent, dry_run=args.dry_run)

    if total == 0:
        return 0
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
