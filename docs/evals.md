# Industrial Evaluation-Driven Development (Evals)

> *"Software tests test your applications. Evals test the AI systems and agents building and driving them."*

This document outlines the **Industrial Evaluation Framework** in `agent-standards`. It provides statistical rigor, deterministic verification gates, and frontier LLM-as-a-judge scoring to benchmark and regression-test coding agent instructions (`AGENTS.md`), skills, models, and scaffolding across codebases.

---

## 1. System Architecture

The evaluation pipeline combines **hard deterministic invariants** with **qualitative multi-dimensional LLM judging** (G-Eval methodology):

```
+-----------------------------------------------------------------------------------------+
|                                    Evaluation Suite                                     |
|                                   (evals/tasks.jsonl)                                   |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                                 Autonomous Agent Loop                                   |
|                             (AGENTS.md + Tools + Model API)                             |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
                      +----------------------+----------------------+
                      |                                             |
                      v                                             v
+------------------------------------------+  +------------------------------------------+
|       1. Deterministic Verification       |  |          2. Qualitative Judge            |
|            (verify.py + Git Diff)        |  |         (LLM-as-a-Judge / G-Eval)        |
+------------------------------------------+  +------------------------------------------+
| • Test command execution (exit 0)        |  | • Faithfulness (1-5): no hallucinated APIs |
| • Blast radius limits (max files touched)|  | • Task completion (1-5): full spec met   |
| • Forbidden paths negative constraints   |  | • Constraint adherence (1-5): boundaries  |
| • Required AST tokens & style invariants |  | • Code quality (1-5): typed, clean, safe |
+------------------------------------------+  +------------------------------------------+
                      |                                             |
                      +----------------------+----------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                            Statistical Analysis & Scorecard                             |
+-----------------------------------------------------------------------------------------+
| • Wilson 95% Confidence Interval: [Lower% - Upper%]                                     |
| • Tail Latency Distribution: p50, p90, p95 percentiles                                  |
| • A/B Regression Delta: Critical regressions, improvements, token spend                 |
| • Visual GitHub Flavored Markdown PR Scorecard                                          |
+-----------------------------------------------------------------------------------------+
```

---

## 2. CLI Execution Standards

From the `agent-standards` root:

```bash
# 1. Quick smoke test (dry-run, no live API spend)
python standards.py eval --repo ../takient --suite smoke --dry-run

# 2. Industrial evaluation with LLM-as-a-Judge (using gpt-4o-mini or gpt-4o)
python standards.py eval --repo ../takient --judge --judge-model gpt-4o-mini

# 3. A/B Regression check against a baseline release with CI failure gate
python standards.py eval --repo ../takient \
  --judge \
  --baseline baseline_v1.0.json \
  --fail-on-regression \
  --output-scorecard pr_scorecard.md \
  --output-json current_run.json
```

---

## 3. Statistical Analysis: Why Wilson Score Intervals?

In production AI engineering, reporting a raw pass rate (e.g. *"8/10 passed = 80%"*) is statistically misleading because sample sizes are small to medium.

`eval_runner.py` computes the **95% Wilson Score Interval**:

$$\hat{p} \pm z \sqrt{\frac{\hat{p}(1-\hat{p})}{n}}$$

For example:
* **8/10 (80.0%)** $\rightarrow$ `95% Wilson CI: [49.0% - 94.3%]` (High uncertainty, do not merge high-risk changes).
* **80/100 (80.0%)** $\rightarrow$ `95% Wilson CI: [71.1% - 86.7%]` (Tight confidence, safe to deploy).

---

## 4. Multi-Dimensional LLM-as-a-Judge Rubric (`judge.py`)

For qualitative outputs that cannot be fully captured by exit codes alone, the judge scores 4 core dimensions on an integer scale (1 to 5):

| Dimension | Weight | Description |
| :--- | :---: | :--- |
| **Faithfulness** | `1.0` | Solution avoids hallucinated APIs and adheres strictly to existing repository architecture. |
| **Task Completion** | `1.5` | Solution completely satisfies all functional and non-functional requirements in the prompt. |
| **Constraint Adherence** | `1.2` | Solution strictly respects negative constraints, file boundaries, and styling rules. |
| **Code Quality** | `1.0` | Code is idiomatic, type-safe, contains proper error handling, and introduces zero security vulnerabilities. |

A composite score is calculated:

$$\text{Composite Score} = \frac{\sum (\text{Score}_i \times \text{Weight}_i)}{\sum \text{Weight}_i}$$

* **Pass Threshold:** Composite Score $\ge 4.0$ AND deterministic verification exit code $== 0$.
* **Offline Fallback:** When `OPENAI_API_KEY` is not present, the judge automatically runs a deterministic AST/diff heuristic analysis with 0ms network latency.

---

## 5. Defining Evaluation Tasks (`evals/tasks.jsonl`)

Each line in `evals/tasks.jsonl` defines an evaluation scenario:

```json
{
  "id": "takient-01-pool-retry",
  "type": "functional_bugfix",
  "prompt": "Fix database connection pool timeout when worker disconnects. Ensure exponential backoff.",
  "target_test": "pytest tests/test_pool.py -k test_timeout",
  "forbidden_paths": ["legacy/**", "deploy/**"],
  "max_files_modified": 2,
  "required_strings": ["retry_count", "backoff_factor"],
  "max_turns": 4,
  "expected_output": "def retry_connection(attempt: int)",
  "rubric": "Must use jittered backoff and log at WARNING level.",
  "tags": ["database", "reliability", "p0"]
}
```

### Supported Schema Fields:

| Field | Type | Required | Description |
| :--- | :--- | :---: | :--- |
| `id` | string | Yes | Unique task identifier |
| `prompt` | string | Yes | Natural language prompt provided to the agent |
| `type` | string | No | Category: `functional_bugfix`, `constraint_compliance`, `security`, `perf` |
| `target_test` | string | No | Test command to execute (default: `python scripts/verify.py`) |
| `forbidden_paths` | list[str] | No | Glob patterns agent must NOT modify |
| `max_files_modified` | int | No | Blast radius cap on number of modified files |
| `required_strings` | list[str] | No | Tokens/AST nodes that must be present in modified files |
| `expected_output` | string | No | Golden reference snippet for pairwise comparison |
| `rubric` | string | No | Custom prompt guidance for the LLM judge |
| `tags` | list[str] | No | Filtering tags (e.g. `["p0", "security"]`) |

---

## 6. Continuous Integration & Pull Request Scorecards

Run automatically on every Pull Request modifying `AGENTS.md`, prompts, or agent skills:

```yaml
# .github/workflows/evals.yml
name: AI Agent Evals
on:
  pull_request:
    paths:
      - "template/AGENTS.md"
      - ".agents/**"
      - "standards.py"

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Download Baseline Eval Report
        run: curl -s https://releases.plaatoos.com/evals/baseline.json -o baseline.json
      - name: Run Evals & Generate Scorecard
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python standards.py eval \
            --judge \
            --baseline baseline.json \
            --fail-on-regression \
            --output-scorecard pr_scorecard.md \
            --output-json current.json
      - name: Publish Scorecard to PR Summary
        if: always()
        run: cat pr_scorecard.md >> $GITHUB_STEP_SUMMARY
```

This guarantees that regressions are caught before PR merge, giving digital native scale-ups the confidence to deploy model and prompt updates autonomously.
