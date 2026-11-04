# agent-standards

The engineering setup shared by emiliano, bobby, moza and yapper, kept in one place:
`verify.py` as the definition of done, `AGENTS.md` instructions that any coding agent reads,
agent skills in `.agents/skills/` (linked for tools that only read their own folder),
commit-message and granularity hooks, CI, Dependabot and PR / task templates.

## Start a new repo

```bash
python standards.py new ../my-project --name my-project --scopes api,web
cd ../my-project
git init && git add -A && git commit -m "chore: start from agent standards"
bash scripts/setup-hooks.sh        # after the first commit: the hook caps commits at 5 files
```

Then fill in the `TODO`s in `AGENTS.md` (repository map, commands, gotchas) and in
`.agents/skills/review-change/SKILL.md`, add the repo's checks to `CHECKS` in `scripts/verify.py`,
and its package managers to `.github/dependabot.yml`.

## Keep existing repos in line

```bash
python standards.py check ../emiliano ../bobby ../moza ../yapper   # exit 1 on any difference
python standards.py check ../moza --diff                            # show what differs
python standards.py sync ../moza                                    # rewrite the shared parts
```

`sync` never commits; review with `git diff` and commit in that repo as usual.

To change a shared file, change it **here**, then `sync` every repo. Editing a shared file in one repo
makes `check` report it until the template or the repo is brought back in line.

## What is shared and what each repo owns

| Synced (must stay identical) | Starting point only (the repo owns it after `new`) |
| :--- | :--- |
| `CLAUDE.md` (points Claude Code at `AGENTS.md`) | `AGENTS.md` sections 3 (scopes) and 5-9 |
| `AGENTS.md` sections 1, 2, 4 and 10 | `CHECKS`, `VENV` and `SKILL_MIRRORS` in `scripts/verify.py` |
| `scripts/verify.py` outside its configuration block | `.agents/skills/` (each repo writes its own) |
| `scripts/setup-hooks.sh` (commit-msg and pre-commit hooks) | `.claude/settings.json` |
| `.claude/hooks/lint_edited.py` | `.github/workflows/ci.yml`, `.github/dependabot.yml` |
| `.commitlintrc.json`, `.github/workflows/lint-commits.yml` | `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/task_spec.yml` |

The lists live at the top of `standards.py` (`SYNCED_FILES`, `SHARED_SECTIONS`).

## Adding a coding agent

See section 10 of `template/AGENTS.md`. Tools that read `AGENTS.md` and `.agents/skills/` need nothing.
For a tool that reads only its own skills folder, add that folder to `SKILL_MIRRORS` in each repo's
`scripts/verify.py` and run `python scripts/verify.py --only skills --fix` there.
