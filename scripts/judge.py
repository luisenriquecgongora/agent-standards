"""
LLM-as-a-Judge Evaluation Engine for Autonomous Coding Agents.

Implements multi-dimensional rubric scoring (G-Eval methodology) for evaluating qualitative
aspects of AI agent code generation, refactoring, and tool usage:
- Faithfulness / Groundedness: Is the solution faithful to instructions without hallucinated APIs?
- Task Completion: Does the solution fully address all requirements of the prompt?
- Constraint Adherence: Did the agent respect negative constraints, paths, and invariants?
- Code Quality & Security: Cleanliness, typing, error handling, and security posture.

Supports:
- OpenAI API models (`gpt-4o`, `gpt-4o-mini`, `o3-mini`) with Strict JSON Structured Outputs.
- Pure Python heuristic judge fallback for offline, dry-run, and air-gapped CI environments.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class JudgeDimension:
    name: str
    description: str
    weight: float = 1.0


DEFAULT_DIMENSIONS = [
    JudgeDimension("faithfulness", "Solution avoids hallucinated APIs and strictly adheres to project architecture.", weight=1.0),
    JudgeDimension("task_completion", "Solution completely implements all functional requirements requested in prompt.", weight=1.5),
    JudgeDimension("constraint_adherence", "Solution strictly respects negative constraints, file boundaries, and styling.", weight=1.2),
    JudgeDimension("code_quality", "Code is clean, properly typed, handles edge cases, and introduces no security flaws.", weight=1.0),
]


@dataclass
class JudgeResult:
    """The outcome of a judge evaluation."""

    task_id: str
    verdict: str  # "PASS" | "FAIL"
    composite_score: float  # Weighted score 1.0 to 5.0
    scores: Dict[str, float]  # Individual dimension scores (1-5)
    reasoning: str  # Explanatory breakdown
    model: str  # Model used for judging (or "heuristic-fallback")
    confidence: float = 1.0  # 0.0 - 1.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


JUDGE_SYSTEM_PROMPT = """You are an expert Principal AI Systems Evaluator assessing code modifications produced by an AI coding agent.
You evaluate the agent's work against a specific task prompt, the resulting git diff, verification test output, and negative constraints.

You must score the following 4 dimensions on a strict 1 to 5 integer scale:
1. faithfulness (1-5): 5 = perfectly grounded in repo APIs, 1 = hallucinated non-existent modules or functions.
2. task_completion (1-5): 5 = all prompt requirements met, 1 = task completely unaddressed or broken.
3. constraint_adherence (1-5): 5 = no forbidden files touched, invariants respected; 1 = breached core constraints.
4. code_quality (1-5): 5 = idiomatic, typed, robust error handling, secure; 1 = brittle, untyped, or introduces security vulnerabilities.

Return your response strictly adhering to the JSON schema with your scores, overall verdict (PASS if composite >= 4.0, else FAIL), and concise reasoning."""


class LLMJudge:
    """
    Evaluates agent outputs using frontier LLMs or a deterministic heuristic grader.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        pass_threshold: float = 4.0,
        dimensions: Optional[List[JudgeDimension]] = None,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.pass_threshold = pass_threshold
        self.dimensions = dimensions or DEFAULT_DIMENSIONS

    def _calculate_composite(self, scores: Dict[str, float]) -> float:
        """Calculates weighted composite score."""
        total_weight = 0.0
        weighted_sum = 0.0
        for dim in self.dimensions:
            score = scores.get(dim.name, 3.0)
            weighted_sum += score * dim.weight
            total_weight += dim.weight
        return round(weighted_sum / total_weight, 2) if total_weight > 0 else 3.0

    def evaluate_heuristic(
        self,
        task_id: str,
        prompt: str,
        git_diff: str,
        test_passed: bool,
        violations: List[str],
        expected_output: Optional[str] = None,
    ) -> JudgeResult:
        """
        Deterministic, fast offline grader when OpenAI API key is unavailable or in dry-run mode.
        """
        scores: Dict[str, float] = {}

        # 1. Constraint adherence
        if violations:
            scores["constraint_adherence"] = max(1.0, 5.0 - (len(violations) * 1.5))
        else:
            scores["constraint_adherence"] = 5.0

        # 2. Task completion
        if not test_passed:
            scores["task_completion"] = 2.0
        elif not git_diff.strip():
            scores["task_completion"] = 1.0  # Claimed passed without modifying anything
        else:
            scores["task_completion"] = 5.0

        # 3. Faithfulness & Code Quality
        code_score = 4.5 if test_passed else 2.5
        # Penalize syntax error markers or TODO leftovers in diff
        if re.search(r"(?i)\b(TODO|FIXME|hack|pass\s*#\s*fixme)\b", git_diff):
            code_score -= 1.0
        # Penalize bare exceptions
        if re.search(r"except\s*:\s*pass", git_diff):
            code_score -= 1.0
        scores["code_quality"] = max(1.0, min(5.0, code_score))
        scores["faithfulness"] = 5.0 if not violations else 3.0

        composite = self._calculate_composite(scores)
        verdict = "PASS" if (composite >= self.pass_threshold and test_passed and not violations) else "FAIL"

        reasons = []
        if test_passed:
            reasons.append("Functional tests passed")
        else:
            reasons.append("Functional tests failed")
        if violations:
            reasons.append(f"{len(violations)} constraint violation(s)")
        if expected_output and expected_output in git_diff:
            reasons.append("Matches golden expected pattern")

        return JudgeResult(
            task_id=task_id,
            verdict=verdict,
            composite_score=composite,
            scores=scores,
            reasoning="; ".join(reasons) + ".",
            model="heuristic-offline",
            confidence=0.85,
            details={"diff_lines": len(git_diff.splitlines()), "violations_count": len(violations)},
        )

    def evaluate(
        self,
        task_id: str,
        prompt: str,
        git_diff: str,
        test_passed: bool,
        violations: List[str],
        notes: str = "",
        expected_output: Optional[str] = None,
        custom_rubric: Optional[str] = None,
    ) -> JudgeResult:
        """
        Runs LLM-as-a-judge evaluation via OpenAI API if key is present,
        or falls back gracefully to deterministic heuristic evaluation.
        """
        if not self.api_key:
            return self.evaluate_heuristic(
                task_id=task_id,
                prompt=prompt,
                git_diff=git_diff,
                test_passed=test_passed,
                violations=violations,
                expected_output=expected_output,
            )

        # Assemble prompt for LLM judge
        eval_payload = {
            "task_id": task_id,
            "prompt": prompt,
            "test_passed": test_passed,
            "violations": violations,
            "git_diff_preview": git_diff[:3000] if git_diff else "(no git diff / no files modified)",
            "expected_output_hint": expected_output or "(none provided)",
            "custom_rubric": custom_rubric or "(standard 4-dimension rubric)",
            "agent_notes": notes,
        }

        user_content = f"Evaluate the following agent task run:\n\n```json\n{json.dumps(eval_payload, indent=2)}\n```"

        schema = {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "properties": {
                        "faithfulness": {"type": "number", "description": "1 to 5 score"},
                        "task_completion": {"type": "number", "description": "1 to 5 score"},
                        "constraint_adherence": {"type": "number", "description": "1 to 5 score"},
                        "code_quality": {"type": "number", "description": "1 to 5 score"},
                    },
                    "required": ["faithfulness", "task_completion", "constraint_adherence", "code_quality"],
                    "additionalProperties": False,
                },
                "reasoning": {"type": "string", "description": "Detailed explanation of scores"},
            },
            "required": ["scores", "reasoning"],
            "additionalProperties": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "judge_evaluation",
                    "strict": True,
                    "schema": schema,
                },
            },
            "temperature": 0.0,
        }

        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result_json = json.loads(resp.read().decode("utf-8"))
                choice = result_json["choices"][0]["message"]["content"]
                parsed = json.loads(choice)
                scores = parsed.get("scores", {})
                reasoning = parsed.get("reasoning", "")
                composite = self._calculate_composite(scores)
                verdict = "PASS" if (composite >= self.pass_threshold and test_passed and not violations) else "FAIL"

                return JudgeResult(
                    task_id=task_id,
                    verdict=verdict,
                    composite_score=composite,
                    scores=scores,
                    reasoning=reasoning,
                    model=self.model,
                    confidence=0.95,
                    details={"api_finish_reason": result_json["choices"][0].get("finish_reason")},
                )
        except Exception as e:
            # On network/API failure, fall back gracefully to heuristic grading
            fallback = self.evaluate_heuristic(
                task_id=task_id,
                prompt=prompt,
                git_diff=git_diff,
                test_passed=test_passed,
                violations=violations,
                expected_output=expected_output,
            )
            fallback.reasoning += f" (Note: OpenAI judge request failed with: {e})"
            return fallback
