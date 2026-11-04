"""Shared engineering standards: start a repo from the template, or keep existing repos in line with it.

Usage:
    python standards.py new <dir> --name <project> --scopes core,api   # new repo from template/
    python standards.py check <repo> [<repo> ...]                      # report drift; exit 1 if any
    python standards.py check <repo> --diff                            # ... with the differences
    python standards.py sync <repo> [<repo> ...]                       # rewrite the shared parts

Only the parts every repo must share are checked and synced (SYNCED_FILES, the body of scripts/verify.py
outside its repo-specific configuration block, and the SHARED_SECTIONS of AGENTS.md). Everything else in
template/ is a starting point that the new repo owns from then on. sync never commits: review with git diff.
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template"

# Identical in every repo.
SYNCED_FILES = [
    "CLAUDE.md",
    ".claude/hooks/lint_edited.py",
    ".commitlintrc.json",
    ".github/workflows/lint-commits.yml",
    "scripts/setup-hooks.sh",
]
# scripts/verify.py: everything except the block between these markers.
VERIFY = "scripts/verify.py"
CONFIG_START = "# --- Repo-specific configuration"
CONFIG_END = "# ----"
# AGENTS.md sections (by number) that are identical in every repo; the others are repo-specific.
AGENTS = "AGENTS.md"
SHARED_SECTIONS = ["1", "2", "4", "10"]


def read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.is_file() else None


def split_verify(text: str) -> tuple[str, str, str]:
    """(before, configuration block, after) of a verify.py."""
    start = text.index(CONFIG_START)
    end = text.index("\n", text.index(CONFIG_END, text.index("\n", start))) + 1
    return text[:start], text[start:end], text[end:]


def agents_sections(text: str) -> dict[str, str]:
    """Section number -> the section's text, heading included."""
    parts = re.split(r"(?m)^(?=### \d+\. )", text)
    return {re.match(r"### (\d+)\.", p).group(1): p for p in parts if p.startswith("### ")}


def expected(repo: Path, rel: str) -> tuple[str | None, list[str]]:
    """The content a repo's file should have, and notes on parts that cannot be synced."""
    template = read(TEMPLATE / rel)
    current = read(repo / rel)
    if rel == VERIFY and current is not None:
        before, _, after = split_verify(template)
        return before + split_verify(current)[1] + after, []
    if rel == AGENTS and current is not None:
        wanted, have = agents_sections(template), agents_sections(current)
        notes = [f"section {n} missing; add it by hand" for n in SHARED_SECTIONS if n not in have]
        for n in SHARED_SECTIONS:
            if n in have:
                # Keep the repo's spacing after the section; compare the section text itself.
                tail = have[n][len(have[n].rstrip("\n")):]
                current = current.replace(have[n], wanted[n].rstrip("\n") + tail, 1)
        return current, notes
    return template, []


def drift(repo: Path, show_diff: bool) -> list[str]:
    problems: list[str] = []
    for rel in SYNCED_FILES + [VERIFY, AGENTS]:
        current = read(repo / rel)
        if current is None:
            problems.append(f"{rel}: missing")
            continue
        want, notes = expected(repo, rel)
        problems += [f"{rel}: {note}" for note in notes]
        if want != current:
            changed = sum(1 for line in difflib.ndiff(current.splitlines(), want.splitlines()) if line[:1] in "+-")
            problems.append(f"{rel}: differs from the template ({changed} lines)")
            if show_diff:
                problems.append("".join(difflib.unified_diff(
                    current.splitlines(True), want.splitlines(True), f"{repo.name}/{rel}", f"template/{rel}")))
    return problems


def sync(repo: Path) -> None:
    for rel in SYNCED_FILES + [VERIFY, AGENTS]:
        target = repo / rel
        if rel in (VERIFY, AGENTS) and not target.is_file():
            print(f"   {rel}: missing; copy it from template/ and fill in the repo-specific parts")
            continue
        want, notes = expected(repo, rel)
        for note in notes:
            print(f"   {rel}: {note}")
        if want != read(target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(want, encoding="utf-8", newline="\n")
            print(f"   updated {rel}")


def new(dest: Path, name: str, scopes: list[str]) -> int:
    if dest.exists() and any(dest.iterdir()):
        print(f"{dest} is not empty; use `sync` for an existing repo", file=sys.stderr)
        return 1
    shutil.copytree(TEMPLATE, dest, dirs_exist_ok=True)
    agents = dest / AGENTS
    scope_list = ", ".join(f"`{s}`" for s in scopes) or "`core`"
    text = agents.read_text(encoding="utf-8").replace("{{SCOPES}}", scope_list)
    agents.write_text(text.replace("# Engineering Standards", f"# {name}: Engineering Standards", 1),
                      encoding="utf-8", newline="\n")
    # Link the shared skills into every SKILL_MIRRORS folder (.claude/skills, ...).
    linked = subprocess.run([sys.executable, str(dest / VERIFY), "--only", "skills", "--fix"])
    print(f"\nCreated {dest}. Next:")
    print("  1. git init && git add -A && git commit -m \"chore: start from agent standards\"")
    print("     then: bash scripts/setup-hooks.sh (after the first commit: the hook caps commits at 5 files)")
    print("  2. Fill in the TODOs in AGENTS.md (sections 6-8) and .agents/skills/review-change/SKILL.md")
    print("  3. Add the repo's checks to CHECKS in scripts/verify.py and its ecosystems to .github/dependabot.yml")
    return linked.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_new = sub.add_parser("new", help="create a repo from the template")
    p_new.add_argument("dest", type=Path)
    p_new.add_argument("--name", required=True)
    p_new.add_argument("--scopes", default="", help="comma-separated commit scopes, e.g. core,api,web")
    p_check = sub.add_parser("check", help="report where repos differ from the template")
    p_check.add_argument("repos", nargs="+", type=Path)
    p_check.add_argument("--diff", action="store_true")
    p_sync = sub.add_parser("sync", help="rewrite the shared parts of repos from the template")
    p_sync.add_argument("repos", nargs="+", type=Path)
    args = parser.parse_args()

    if args.command == "new":
        return new(args.dest, args.name, [s.strip() for s in args.scopes.split(",") if s.strip()])
    failed = False
    for repo in (r.resolve() for r in args.repos):
        if args.command == "sync":
            print(f"== {repo.name}")
            sync(repo)
            continue
        problems = drift(repo, args.diff)
        print(f"== {repo.name}: {'in line with the template' if not problems else f'{len(problems)} difference(s)'}")
        for problem in problems:
            print(f"   {problem}")
        failed |= bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
