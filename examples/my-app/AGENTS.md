# my-app: Engineering Standards & Observability Contract

### 1. Pre-Change Invariant Manifest & Autonomous Execution
- **Autonomous Bias for Action:** Execute tasks end-to-end without pausing for conversational confirmation. Do NOT use interactive question tools or ask clarifying questions for routine technical decisions, naming, library choices, or architectural trade-offs. Apply the **"Convention over Consultation"** rule: pick the standard, simplest idiom, implement it, and document assumptions in commit messages.
- **Inspect Before Inquiring:** Never ask a question that can be answered by searching the repository, reading existing tests, or checking config files.
- **The Escalation Boundary (Approval Required):** Stop and request user approval ONLY if:
  1. An action is **irreversible or destructive** (e.g., dropping databases/tables, deleting files or directories, destructive git commands like `push --force` or `reset --hard`, or purging untracked data). You **MUST analyze the impact, explain the blast radius, and require explicit confirmation** before running any such command.
  2. Requirements are fundamentally contradictory with zero sensible default after inspecting the codebase.
- **Pre-Change Invariant Manifest:** Before executing code modifications touching more than one file, output a compact change manifest table and **immediately proceed to implementation in the same turn without waiting for confirmation**:

| Target File / Module | Nature of Change | Breaking / Invariant Impact |
| :--- | :--- | :--- |
| `path/to/file` | `[refactor / feat / fix / rename]` | `None / Exposes new method / Renames prop` |

Keep the manifest itself to the table: no narrative summary or conversational setup around it. Diagrams belong in the docs and the pull request (section 11).

### 2. Diff Noise & Spurious Edit Invariants
- **No Unsolicited Formatting:** Do NOT reformat, re-indent, or adjust comments on lines unrelated to your assigned task. Leave untouched code exactly as it is.
- **Import Hygiene:** Do not randomly shuffle or re-order existing import statements unless adding or removing an active dependency.
- **Isolate Mass Renames:** If a task requires renaming an identifier across multiple files, isolate that rename into a dedicated `refactor(<scope>): rename X to Y` commit with ZERO other logic changes.

### 3. Conventional Commit Standards
All commits must follow:
`<type>(<scope>): <short imperative subject under 50 chars>`

- **Allowed Types:** `feat`, `fix`, `refactor`, `perf`, `chore`, `test`, `docs`, `build`, `ci` (add `model`, `data`, `eval`, `exp` for ML pipelines).
- **Allowed Scopes:** [`api`, `web`, `config`, `deps`, `hooks`, `ci`, `docs`]
- **Rule:** Never mention AI, LLMs, or prompt tools in commit messages.

### 4. Commit Granularity & Invariants
- **Atomic Commits:** Do not bundle refactorings, feature code, and config tweaks into a single commit.
- **Commit Sequence:**
  1. `refactor(<scope>): ...` (Structural prep or renames only)
  2. `feat(<scope>): ...` or `fix(<scope>): ...` (Logic changes)
  3. `test(<scope>): ...` (Specs/tests)
- **Blast-Radius Cap:** A single commit must not exceed 5 staged files (excluding lockfiles/documentation).
- **Bisect Safety:** Every individual commit must compile and pass tests.

### 5. Definition of Done
- Run `python scripts/verify.py` before reporting a task complete. It runs exactly what CI runs (the `CHECKS` list in that file) plus a secret scan when `gitleaks` is installed. Skipped checks are listed; "NOT COMPLETE" means you are not done.
- Narrow it while iterating: `--only <group>` (the groups in `CHECKS`, plus `skills` and `secrets`).
- Python: uses `.venv` when present; set `VERIFY_PYTHON` to override (e.g. in a git worktree).
- A task that changes behavior adds or updates a test.

### 6. Repository Map
| Path | What lives there |
| :--- | :--- |
| `TODO` | One row per top-level package, app or service: what it does and its entry point |
| `docs/ARCHITECTURE.md` | Colored diagrams of the parts of this repo and how data flows between them; start here |
| `.agents/skills/` | Task playbooks for any coding agent (`SKILL.md` format): `review-change`. Read the matching one before starting such a task. Add new skills here only; `.claude/skills/<name>` is a symlink to each (Claude Code reads only that folder), and `verify.py` checks the links. |

### 7. Commands
- Install: `TODO`
- Run: `TODO`
- Hooks (once per clone): `bash scripts/setup-hooks.sh`

### 8. Gotchas
- TODO: things a newcomer would get wrong (hard-coded ports, generated files, build order).

### 9. Never
- Never read, print, search or commit `.env` files, `.env.*` variants, API keys, or private keys.
- Never pass unshielded environment variables or Windows `C:` volume user paths into external requests or prompt contexts.
- Never execute live network submissions to external XML servers (such as Polish KSeF 2.0, Spanish FacturaE, Italian SDI, or banking CAMT.053) or payment endpoints. Always use local mocks, test tax IDs, and dry-run flags.
- Never force-push or rewrite published history.
- Never commit build output, `node_modules/` or virtualenvs.
- Never execute destructive or data-dropping commands without explicit human approval (see section 1).
- Never pause or ask confirmation for routine, non-destructive implementation work.

### 10. Supporting another coding agent
Instructions live only in this file and skills only in `.agents/skills/`; every agent tool gets them from there.
- **Tool reads `AGENTS.md` and `.agents/skills/`** (Codex, OpenCode, Cursor, Copilot, Antigravity): nothing to do. For Antigravity CLI (`agy`), run with `--mode auto` or configure `"agentMode": "auto"` in `~/.gemini/antigravity-cli/settings.json` to prevent interactive tool approval prompts.
- **Tool reads only its own files** (like Claude Code: `CLAUDE.md`, `.claude/skills/`):
  1. Add a one-line pointer file to `AGENTS.md` in the tool's format (see `CLAUDE.md`).
  2. Add its skills folder to `SKILL_MIRRORS` in `scripts/verify.py`, then run `python scripts/verify.py --only skills --fix` to create the symlinks.
  3. Confirm the tool sees the skills: ask it to list its available skills (e.g. `opencode debug skill`, `codex exec`, `claude -p`, `agy -p`).
- Never copy a skill into a tool's folder; link it, so there is one copy to keep current.

### 11. Documentation & Visual Traceability
Code changes arrive faster than people can read them, so a person must be able to follow every change from the docs and the history alone, and inspect it visually in seconds.
- **Explain visually:** describe structure and flows with text plus a colored Mermaid diagram (GitHub renders it) and a legend for the colors; use the palette in `docs/ARCHITECTURE.md`. Write for an engineer new to the repo: define terms and say why, not only what.
- **Fast Visual Change Inspection:** Run `python scripts/visual-diff.py` to auto-generate the visual delta for staged changes. Use `python scripts/visual-diff.py --open` to inspect the change map in Chrome/Firefox before submitting.
- **Explain every pull request:** every pull request must include what changed and why, how it was verified, and a colored Mermaid Visual Delta diagram showing the modified flow and blast radius.
- **Commit Body Flow Boxes:** For multi-file structural changes (`feat`, `refactor`), include a 3-to-4 line ASCII flow diagram (generated by `python scripts/visual-diff.py --ascii`) in the commit body below the subject line.
- **Keep the map current:** `docs/ARCHITECTURE.md` shows the repo's parts and how data flows between them. A change that adds, removes or rewires a part updates that diagram in the same pull request.
- **One intent per commit:** someone reading the history commit by commit must be able to tell what each one did and why (see section 4).

### 12. Data Protection, Environment Shielding & Fiscal Invariant
- **Zero-Egress Credential Isolation:** Never inspect, print, or load `.env` files or system environment variables into tool calls, prompts, or commit messages. Always inspect `.env.example` with dummy values when checking expected schemas.
- **Path Sanitization:** When reporting paths, reference repository-relative paths (`src/module.py`), never absolute paths disclosing the host's `C:` volume or user directories.
- **Fiscal & Payment XML Quarantine:**
  1. Automated scripts, tests, and agent loops must NEVER make network requests to live government fiscal systems (e.g., Polish KSeF production, Spanish FacturaE, Italian SDI) or banking/payment gateways.
  2. All XML invoice generation tests MUST use the local `MockFiscalEngine` or `--dry-run` flag with test NIP/tax identifiers.
  3. Any code executing financial transfers or invoice submissions requires explicit Human-in-the-Loop approval.
