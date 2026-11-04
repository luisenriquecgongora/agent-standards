# Glossary

Every term these docs use, in one or two plain sentences. Alphabetical.

**Agent / coding agent**
A program that reads and edits code for you from instructions in plain language: Claude Code, Codex,
OpenCode, Cursor, Copilot, Antigravity. In these docs, "the agent" is whichever one you use.

**`.agent-standards` (the stamp)**
A small file at the root of every repo that uses these standards: **one per repo, never in subfolders**. It
records which version of the standards the repo has and which stacks it uses, e.g.
`{"version": "1.1.1", "stacks": ["python", "node"]}`. `check` and `sync` find repos by looking for this file.
See [the README](../README.md#the-agent-standards-file).

**`AGENTS.md`**
A file of instructions at the root of a repo, written for coding agents (and useful to people too): how to
commit, how to check work, what lives where, what never to do. Most agents read it automatically.

**CI (continuous integration)**
Checks that GitHub runs automatically on every push and pull request. Here, CI runs `verify.py`, a scan for
leaked secrets and a check of commit messages. Defined in `.github/workflows/`.

**`CLAUDE.md`**
Claude Code reads `CLAUDE.md` instead of `AGENTS.md`. Ours contains one line, `@AGENTS.md`, which tells Claude
Code to read `AGENTS.md`, so every agent follows the same instructions.

**Commit hooks (git hooks)**
Small scripts git runs on your machine when you commit. Ours check the commit message format and the size and
content of the commit, and reject the commit if a rule is broken. Installed once per clone with
`bash scripts/setup-hooks.sh`.

**Conventional commit**
The commit message format we use: `<type>(<scope>): <what changed>`, e.g. `fix(api): handle empty request`.
See [using-a-repo.md](using-a-repo.md#3-commit-the-way-the-hooks-expect).

**Definition of done**
The single rule for when a task is finished. Here: `python scripts/verify.py` passes.

**Dependabot**
A GitHub feature that opens pull requests to update your dependencies (libraries). Configured in
`.github/dependabot.yml`.

**Discovery / discover root**
How `check` and `sync` find repos when you do not name them: they search the folder above `agent-standards`
(the *discover root*) and one level below it for `.agent-standards` files. Set in `standards.json`.

**Drift**
When a repo's copy of a shared file no longer matches the template, because someone edited it in that repo
or the repo has not been synced since the template changed. `check` reports drift.

**Lint / linter**
A tool that reads code and reports likely mistakes without running it: unused imports, undefined names, and
so on. `ruff` is the Python linter we use.

**Lint-on-edit hook**
A script (`.claude/hooks/lint_edited.py`) that runs the linter on each file right after an agent edits it,
and sends any problems back to the agent so it fixes them immediately.

**Preset**
The files that describe one stack, in `presets/<stack>/`: its checks, its lint-on-edit rule, its CI setup
steps, its Dependabot entry and its `.gitignore` lines.

**Pull request (PR)**
A request on GitHub to merge a branch into another. CI runs on it, and a person reviews it.

**Repo (repository)**
A project folder tracked by git, usually also on GitHub.

**Scope**
The part of a repo a commit changes, written in brackets in the commit message: `fix(api): ...`. Each repo
lists its scopes in section 3 of its `AGENTS.md`.

**Shared / synced**
Files (or parts of files) that must be identical in every repo. `sync` keeps them identical; everything else
in a repo belongs to that repo. See [reference.md](reference.md#what-is-shared-and-what-each-repo-owns).

**Skill**
A step-by-step playbook for a recurring task (for example "review a change"), in
`.agents/skills/<name>/SKILL.md`. Agents read the matching skill before starting that kind of task.

**Stack**
A language and its tools: `python`, `node` or `rust` so far. You choose stacks when you create a repo, and
each one adds its own checks and settings.

**Symlink (symbolic link)**
A file system entry that points to another file or folder, like a shortcut. `.claude/skills/<name>` is a
symlink to `.agents/skills/<name>`, so the skill exists once but Claude Code can find it in its own folder.

**Template**
The `template/` folder of this repo: the base files every new repo starts from.

**`verify.py`**
`scripts/verify.py`: the script that runs every check CI runs, in one command. See *definition of done*.
