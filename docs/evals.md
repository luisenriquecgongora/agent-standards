# Evaluation-Driven Development (Evals)

How to measure and regression-test coding agent instructions (`AGENTS.md`), skills, and scaffolding across your repositories.

## Overview

Software tests (`scripts/verify.py`) test your **applications**.  
AI Evals test the **AI developers** writing code in those applications.

When you modify instructions in `template/AGENTS.md` or add a new skill to `agent-standards`, running an eval ensures that your changes actually improve agent capability and don't cause subtle regressions across downstream codebases.

```
Task (tasks.jsonl) ➔ Agent Loop (AGENTS.md + Tools) ➔ Code Changes ➔ Grader (verify.py + Invariants) ➔ Scorecard
```

## Running Evals

From `agent-standards`:

```bash
# Evaluate a specific downstream repo
python standards.py eval --repo ../takient

# Run a quick smoke test (first task only)
python standards.py eval --repo ../takient --suite smoke

# Dry-run (validates task definitions without calling live LLMs)
python standards.py eval --repo ../takient --dry-run

# Run with a live coding agent CLI
python standards.py eval --repo ../takient --agent "claude -p"
```

## Defining Evaluation Tasks (`evals/tasks.jsonl`)

Each managed repository can maintain an `evals/tasks.jsonl` file with representative tasks (historical bug fixes, feature requests, or invariant checks).

Each line in `evals/tasks.jsonl` is a JSON object with the following fields:

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `id` | string | Yes | Unique task identifier (e.g., `takient-01-harness-parity`) |
| `prompt` | string | Yes | The natural language task prompt given to the AI agent |
| `type` | string | No | Category: `functional_bugfix`, `constraint_compliance`, `design_system_rule`, etc. |
| `target_test` | string | No | Test command to execute (default: `python scripts/verify.py`) |
| `forbidden_paths` | list[string] | No | Glob patterns of paths the agent must NOT modify (e.g., `["ai-services/**"]`) |
| `max_files_modified` | integer | No | Blast radius cap: max number of files the agent may touch (e.g., `5`) |
| `required_strings` | list[string] | No | Text or tokens that MUST be present in modified files (e.g., `["py-20"]`) |
| `max_turns` | integer | No | Maximum turn budget before timing out (default: `5`) |

### Example `evals/tasks.jsonl`

```json
{"id": "task-01-bugfix", "type": "functional_bugfix", "prompt": "Fix connection pool timeout when worker disconnects.", "target_test": "pytest tests/test_pool.py -k test_timeout"}
{"id": "task-02-guard", "type": "constraint_compliance", "prompt": "Add fitness business logic without modifying deprecated services.", "target_test": "pytest tests/test_business.py", "forbidden_paths": ["legacy/**"], "max_files_modified": 3}
{"id": "task-03-ui", "type": "design_system_rule", "prompt": "Create owner banner adhering to container padding rules.", "target_test": "npm test", "required_strings": ["py-20", "#14B8A6"]}
```

## Recommended Workflow

1. **Before Syncing Standards**:
   - You make edits to `template/AGENTS.md` or `.agents/skills/`.
   - Run `python standards.py eval --repo ../takient` (and any other pilot repos).
   - If score is 100%, run `python standards.py sync` with confidence.
2. **In CI/CD**:
   - Add `.github/workflows/evals.yml` to run `python standards.py eval` automatically on Pull Requests that touch `AGENTS.md` or shared templates.
