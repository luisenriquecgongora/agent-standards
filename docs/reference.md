# Reference

Look-up tables. For step-by-step guides see [using-a-repo.md](using-a-repo.md),
[new-project.md](new-project.md) and [maintaining.md](maintaining.md).

## standards.py commands

Run from the `agent-standards` folder.

| Command | What it does | Changes files? |
| :--- | :--- | :--- |
| `python standards.py stacks` | Lists the available stacks | No |
| `python standards.py new <folder> --name <name> [--stack a,b] [--scopes x,y]` | Creates a repo from the template. Refuses a non-empty folder | Creates the new folder only |
| `python standards.py check [<repo> ...] [--diff]` | Reports where repos differ from the template. Exit code 1 if any does | No |
| `python standards.py sync [<repo> ...]` | Rewrites the shared parts of repos, prints the changelog since each repo's version | Yes, shared parts only; never commits |

Without repo arguments, `check` and `sync` use every repo with an `.agent-standards` file under the
discover root (see `discover` in `standards.json`).

## What is shared and what each repo owns

Set in `standards.json`.

| Shared: identical in every repo, updated by `sync` | Owned: a starting point, the repo changes it freely |
| :--- | :--- |
| `CLAUDE.md` | `AGENTS.md` sections 3 (commit scopes), 5 to 9 (definition of done, repo map, commands, gotchas, never) |
| `AGENTS.md` sections 1, 2, 4 and 10 | The configuration block of `scripts/verify.py`: `VENV`, `CHECKS`, `EDIT_LINTERS`, `SKILL_MIRRORS` |
| `scripts/verify.py`, except its configuration block | `.agents/skills/` (each repo writes its own skills) |
| `scripts/setup-hooks.sh` | `.claude/settings.json` |
| `.claude/hooks/lint_edited.py` | `.github/workflows/ci.yml`, `.github/dependabot.yml` |
| `.commitlintrc.json` | `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/task_spec.yml` |
| `.github/workflows/lint-commits.yml` | `.gitignore` |
| | `.agent-standards` (its `version` is updated by `sync`; `stacks` is yours) |

## Every file in a new repo

What `python standards.py new my-app --stack python,node --scopes api,web` creates (the full result is in
[`examples/my-app/`](../examples/my-app/)). `[synced]` = shared, see above.

```
my-app/
├── .agents/
│   └── skills/
│       └── review-change/
│           └── SKILL.md          ← review checklist; add the repo's own skills next to it
├── .claude/
│   ├── hooks/
│   │   └── lint_edited.py        ← lints each file an agent edits (EDIT_LINTERS in verify.py)  [synced]
│   ├── skills/
│   │   └── review-change -> ../../.agents/skills/review-change   ← symlink, for Claude Code
│   └── settings.json             ← what Claude Code may and may not do; turns on the lint hook
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   └── task_spec.yml         ← "Task spec" form: a task an agent or a person can pick up
│   ├── workflows/
│   │   ├── ci.yml                ← runs verify.py and a secret scan, with each stack's setup steps
│   │   └── lint-commits.yml      ← checks commit messages on pull requests  [synced]
│   ├── dependabot.yml            ← dependency update PRs: pip, npm and GitHub Actions
│   └── PULL_REQUEST_TEMPLATE.md
├── scripts/
│   ├── setup-hooks.sh            ← installs the commit hooks, once per clone  [synced]
│   └── verify.py                 ← definition of done: ruff, pytest and tsc for these stacks  [synced, except its configuration block]
├── .agent-standards              ← {"version": "1.1.0", "stacks": ["python", "node"]}
├── .commitlintrc.json            ← commit message rules used by CI  [synced]
├── .gitignore                    ← .env, plus each stack's folders: .venv/, __pycache__/, node_modules/, dist/, ...
├── AGENTS.md                     ← instructions for every coding agent; scopes `api`, `web`  [sections 1, 2, 4, 10 synced]
└── CLAUDE.md                     ← "@AGENTS.md": Claude Code reads the same instructions  [synced]
```

## AGENTS.md sections

| # | Section | Shared? | Contents |
| :--- | :--- | :--- | :--- |
| 1 | Pre-Change Invariant Manifest | Yes | List the files a multi-file change touches before making it |
| 2 | Diff Noise & Spurious Edit Invariants | Yes | No unrelated reformatting, no import reshuffling, renames in their own commit |
| 3 | Conventional Commit Standards | No | Message format, types, **this repo's scopes** |
| 4 | Commit Granularity & Invariants | Yes | Atomic commits, refactor → feat/fix → test, 5-file cap, every commit passes |
| 5 | Definition of Done | No | What `verify.py` runs in this repo |
| 6 | Repository Map | No | What lives where, including the list of skills |
| 7 | Commands | No | Install, run, test |
| 8 | Gotchas | No | What newcomers get wrong |
| 9 | Never | No | Hard rules: secrets, force-push, personal data, ... |
| 10 | Supporting another coding agent | Yes | How a new agent gets the same instructions and skills |

## verify.py configuration block

Between `# --- Repo-specific configuration` and the closing `# -----` line near the top of `scripts/verify.py`.

| Setting | Type | Meaning |
| :--- | :--- | :--- |
| `VENV` | path | Virtual environment whose Python runs `{py}` checks, when it exists. Override with `VERIFY_PYTHON` |
| `CHECKS` | list of `(group, name, folder, command)` | Every check, run in order. `--only <group>` runs one group |
| `EDIT_LINTERS` | `{extension: command}` | The linter the lint-on-edit hook runs for each file type; `{file}` is the edited file |
| `SKILL_MIRRORS` | list of folders | Folders of agents that only read their own skills folder; each gets a link to every skill |

Command tokens:

| Token | Becomes |
| :--- | :--- |
| `{py}` | The repo's Python (`VERIFY_PYTHON`, else `VENV`, else the Python running verify.py) |
| `{ruff}` | `ruff` from that Python, else from PATH |
| `{yarn}` | `yarn` from PATH |
| `{gitleaks}` | `gitleaks` from PATH (the secret scan) |
| any other `{tool}` | That tool from PATH, e.g. `{cargo}`, `{go}` |
| `{file}` | `EDIT_LINTERS` only: the edited file |

A check whose tool or folder is missing is **skipped** and listed under "NOT COMPLETE"; it does not fail.
`yarn` checks are also skipped until `yarn install` has run.

verify.py options: `--only <group>` (one group, including `skills` and `secrets`), `--fix` (create missing
skill links).

## Git hooks

Installed by `bash scripts/setup-hooks.sh`.

| Hook | Rejects a commit when |
| :--- | :--- |
| `commit-msg` | The first line is not `<type>(<scope>)!: <description>` (scope and `!` optional, description up to 72 characters). Exempt: `Merge `, `Revert "`, `fixup!`, `squash!`, `amend!` |
| `pre-commit` | Trailing whitespace or line-ending errors are staged |
| `pre-commit` | More than 5 counted files are staged (12 when all are inside one `packages/<x>/` or `apps/<x>/`). Not counted: lockfiles, `.md`, `.test.`/`.spec.` files, migrations, `.sql`, `locales/` and `i18n/` JSON, `.gitattributes`, `.editorconfig` |
| `pre-commit` | Build configuration (`tsconfig`, `.eslintrc`, `vite.config`, `webpack`, `Dockerfile`, `.env`, `CMakeLists.txt`) is staged together with source under `src/`, `lib/`, `packages/` or `apps/` |

Hooks that existed before are kept as `<hook>.local` and run after ours.

## This repo

```
agent-standards/
├── standards.py        ← the new / check / sync / stacks commands
├── standards.json      ← what is shared, current version, where to discover repos
├── CHANGELOG.md        ← what changed in each version; sync prints it
├── template/           ← the base files of every new repo
├── presets/            ← one folder per stack: preset.json, ci-steps.yml, dependabot.yml
├── examples/my-app/    ← a generated repo, kept current by a test
├── tests/              ← pytest suite run by CI
└── docs/               ← these guides
```
