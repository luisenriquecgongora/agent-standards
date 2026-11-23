# Changelog

Bump `version` in `standards.json` whenever a synced part changes, and add an entry here:
`sync` shows each repo the entries newer than the version in its `.agent-standards` stamp.

## 1.4.3
- Automated UI & Desktop Visual Snapshots (Horizon 2):
  - Added UI & styling component detection (`.tsx`, `.jsx`, `.vue`, `.css`, templates) to `scripts/visual-diff.py`.
  - Added automated before/after image diffing via PIL with 3-panel composite strips (`[Before] ──► [Pixel Diff Highlight] ──► [After]`).
  - Added `UI & Visual Layer` assessment dimension to the PR Risk Radar.
  - Added dedicated UI visual changes section to PR markdown and browser viewer (`--open`).

## 1.4.2
- Semantic AST Call-Graph & PR Risk Radar:
  - Added AST symbol parsing (Python `ast` & TypeScript/JavaScript route/symbol extraction) to `scripts/visual-diff.py`.
  - Added automated PR Risk Radar & Blast Radius Scorecard (triage assessment, blast radius, schema impact, API route changes, test invariants).
  - Enhanced Mermaid flowchart with semantic sub-nodes for modified/added functions and endpoints.
  - Enhanced ASCII commit flow boxes with symbol-level indentation.

## 1.4.1
- Automated PR & Commit Diagrams:
  - Added `.github/workflows/pr-visual-summary.yml`: automatically generates and updates a sticky PR comment on GitHub with native SVG Mermaid architecture deltas on every pull request.
  - Added `prepare-commit-msg` hook to `scripts/setup-hooks.sh`: automatically embeds monospace ASCII flow delta diagrams into multi-file commit bodies, permanently preserving them on GitHub commit pages and `git log`.

## 1.4.0
- Visual Change & Architecture Traceability:
  - Added `scripts/visual-diff.py` to auto-generate Mermaid architecture flowcharts, ASCII commit boxes, and interactive browser reports (`scripts/visual-diff.py --open`).
  - Added `scripts/open-artifact.py` to render any markdown plan/artifact with Mermaid into standalone HTML and launch directly in Chrome/Firefox.
  - Updated `.github/PULL_REQUEST_TEMPLATE.md` with the standard ⚡ Visual Delta section for fast human PR inspection.
  - Updated `AGENTS.md` section 11 to require visual delta inspection before PR/commit.
  - Updated `.agents/skills/review-change/SKILL.md` to checklist visual inspection.

## 1.3.0
- Added secret scanning and confidential data shielding to verify.py and pre-commit hooks.

## 1.2.3
- `AGENTS.md` section 1: Added Autonomous Execution Guidelines (high bias for action, zero unnecessary questions, convention over consultation, inspect before inquiring, escalation boundary, non-blocking manifest execution).
- `AGENTS.md` section 10: Documented AGY (`agy`) `--mode auto` / `settings.json` configuration to prevent interactive tool approval prompts.
- `AGENTS.md` section 9: Linked "never" actions with the section 1 escalation boundary.
- Nothing to do in repos besides `sync`.

## 1.2.2
- `verify.py`: fail in CI / strict mode if any configured check in `CHECKS` is skipped (due to missing directory or uninstalled tool). Prevents false-green CI builds. Added `--strict`, `--allow-skipped`, and `-v/--verbose` logging flags.
- Nothing to do in repos besides `sync`.

## 1.2.1
- `AGENTS.md` section 1: no longer reads as "never draw diagrams". It now limits only the pre-change manifest to its table, and points to section 11 for diagrams, which removes a contradiction with section 11.
- Nothing to do in repos besides `sync`.

## 1.2.0
- `AGENTS.md`: new shared section 11, *Documentation & Traceability*: explain structure and flows with text plus colored diagrams, keep `docs/ARCHITECTURE.md` current in the same pull request, explain every pull request, one intent per commit.
- `sync` now adds a shared `AGENTS.md` section a repo does not have yet, instead of asking you to add it by hand.
- New repos get a `docs/ARCHITECTURE.md` starter with the color palette.
- `check` and `sync` without arguments now start from the folder you run them in, like git: inside a repo they use that repo; in a folder of repos, every managed repo in it. `agent-standards` no longer has to sit next to the repos; `--root` picks another folder.
- **In each repo:** after `sync`, add `docs/ARCHITECTURE.md` (copy `template/docs/ARCHITECTURE.md` and draw the repo's real parts) and list it in `AGENTS.md` section 6.

## 1.1.1
- `verify.py`: a `VERIFY_PYTHON` that does not exist now stops with a clear message instead of a traceback. It may also name a program on PATH, e.g. `VERIFY_PYTHON=python3.12`.
- `lint_edited.py`: stays silent in that case instead of failing.
- Nothing to do in repos besides `sync`.

## 1.1.0
- `verify.py`: any `{tool}` in a check (e.g. `{cargo}`, `{go}`) is looked up on PATH; a missing tool skips the check.
- `verify.py`: new `EDIT_LINTERS` setting in the configuration block: the linter to run per file extension when an agent edits a file.
- `lint_edited.py`: runs `EDIT_LINTERS` instead of always ruff. Repos whose configuration has no `EDIT_LINTERS` keep ruff on `.py` files.
- `setup-hooks.sh`: `poetry.lock`, `Cargo.lock`, `go.sum`, `Gemfile.lock` and `composer.lock` no longer count toward the 5-file commit cap.

## 1.0.0
- The setup shared by emiliano, bobby, moza and yapper: `verify.py` with agent-skill checks, `AGENTS.md` sections 1, 2, 4 and 10, commit hooks, the edit-lint hook and commit linting.
