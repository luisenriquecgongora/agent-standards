# Changelog

Bump `version` in `standards.json` whenever a synced part changes, and add an entry here:
`sync` shows each repo the entries newer than the version in its `.agent-standards` stamp.

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
