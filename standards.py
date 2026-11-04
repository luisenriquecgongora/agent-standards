"""Shared engineering standards: start a repo from the template, or keep existing repos in line with it.

Usage:
    python standards.py new <dir> --name <project> [--stack python,node] [--scopes core,api]
    python standards.py check [<repo> ...] [--diff]   # report drift; exit 1 if any
    python standards.py sync [<repo> ...]             # rewrite the shared parts, show what changed
    python standards.py stacks                        # list the available stacks

Without repos, check and sync use every repo with an .agent-standards stamp found under the
discover root in standards.json. What is shared lives in standards.json; stack add-ons live in
presets/<stack>/. Everything else in template/ is a starting point the new repo owns from then on.
sync never commits: review with git diff.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template"
PRESETS = HERE / "presets"
CONFIG = json.loads((HERE / "standards.json").read_text(encoding="utf-8"))
VERSION = CONFIG["version"]
VERIFY = CONFIG["verify"]["path"]
AGENTS = CONFIG["agents"]["path"]
STAMP = CONFIG["stamp"]

# Lines in template files that `new` replaces with stack content.
CHECKS_LINE = "CHECKS: list[tuple[str, str, str, list[str]]] = []\n"
LINTERS_LINE = "EDIT_LINTERS: dict[str, list[str]] = {}\n"
CI_MARKER = "      # standards: stack setup steps\n"
DEPENDABOT_MARKER = "  # standards: stack ecosystems\n"


def read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.is_file() else None


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version))


# --- Shared parts ---------------------------------------------------------------


def split_verify(text: str) -> tuple[str, str, str]:
    """(before, configuration block, after) of a verify.py."""
    start = text.index(CONFIG["verify"]["config_start"])
    end_marker = text.index(CONFIG["verify"]["config_end"], text.index("\n", start))
    end = text.index("\n", end_marker) + 1
    return text[:start], text[start:end], text[end:]


def agents_sections(text: str) -> dict[str, str]:
    """Section number -> the section's text, heading included."""
    parts = re.split(r"(?m)^(?=### \d+\. )", text)
    return {re.match(r"### (\d+)\.", p).group(1): p for p in parts if p.startswith("### ")}


def shared_paths() -> list[str]:
    return CONFIG["synced_files"] + [VERIFY, AGENTS]


def expected(repo: Path, rel: str) -> tuple[str | None, list[str]]:
    """The content a repo's file should have, and notes on parts that cannot be synced."""
    template = read(TEMPLATE / rel)
    current = read(repo / rel)
    if rel == VERIFY and current is not None:
        before, _, after = split_verify(template)
        return before + split_verify(current)[1] + after, []
    if rel == AGENTS and current is not None:
        wanted, have = agents_sections(template), agents_sections(current)
        shared = CONFIG["agents"]["shared_sections"]
        for n in shared:
            if n in have:
                tail = have[n][len(have[n].rstrip("\n")):]  # keep the repo's spacing after it
                current = current.replace(have[n], wanted[n].rstrip("\n") + tail, 1)
        # A shared section the repo lacks goes before its next higher-numbered section, or at the end.
        for n in sorted((n for n in shared if n not in have), key=int):
            section = wanted[n].rstrip("\n") + "\n"
            later = sorted((k for k in agents_sections(current) if int(k) > int(n)), key=int)
            if later:
                nxt = agents_sections(current)[later[0]]
                current = current.replace(nxt, section + "\n" + nxt, 1)
            else:
                current = current.rstrip("\n") + "\n\n" + section
        return current, []
    return template, []


def read_stamp(repo: Path) -> dict | None:
    text = read(repo / STAMP)
    return json.loads(text) if text else None


def write_stamp(repo: Path, stacks: list[str]) -> None:
    write(repo / STAMP, json.dumps({"version": VERSION, "stacks": stacks}, indent=2) + "\n")


def changes_since(version: str | None) -> str:
    """CHANGELOG entries newer than version (all of them when version is None)."""
    text = read(HERE / "CHANGELOG.md") or ""
    entries = re.split(r"(?m)^(?=## )", text)
    newer = [e for e in entries if e.startswith("## ")
             and (version is None or version_tuple(e[3:].split()[0]) > version_tuple(version))]
    return "".join(newer).strip()


def drift(repo: Path, show_diff: bool) -> list[str]:
    problems: list[str] = []
    stamp = read_stamp(repo)
    if stamp is None:
        problems.append(f"{STAMP}: missing (sync creates it)")
    elif stamp.get("version") != VERSION:
        problems.append(f"{STAMP}: on {stamp.get('version')}, template is {VERSION}")
    for rel in shared_paths():
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
    stamp = read_stamp(repo)
    if stamp is None or stamp.get("version") != VERSION:
        since = stamp.get("version") if stamp else None
        print(f"   {'no stamp yet' if since is None else f'{since} -> {VERSION}'}; changes:")
        print("\n".join(f"     {line}" for line in changes_since(since).splitlines()))
    for rel in shared_paths():
        target = repo / rel
        if rel in (VERIFY, AGENTS) and not target.is_file():
            print(f"   {rel}: missing; copy it from template/ and fill in the repo-specific parts")
            continue
        want, notes = expected(repo, rel)
        for note in notes:
            print(f"   {rel}: {note}")
        if want != read(target):
            write(target, want)
            print(f"   updated {rel}")
    write_stamp(repo, stamp.get("stacks", []) if stamp else [])
    if stamp is None:
        print(f"   created {STAMP}: list the repo's stacks in it ({', '.join(available_stacks())})")


def discover() -> list[Path]:
    """Repos with a stamp under the discover root."""
    root = (HERE / CONFIG["discover"]["root"]).resolve()
    found = []
    for depth in range(1, CONFIG["discover"]["max_depth"] + 1):
        found += [p.parent for p in root.glob("/".join(["*"] * depth) + "/" + STAMP)]
    return sorted(p for p in set(found) if p.resolve() != HERE)


# --- New repos ------------------------------------------------------------------


def available_stacks() -> list[str]:
    return sorted(p.name for p in PRESETS.iterdir() if (p / "preset.json").is_file())


def load_preset(stack: str) -> dict:
    folder = PRESETS / stack
    preset = json.loads((folder / "preset.json").read_text(encoding="utf-8"))
    preset["dependabot_yml"] = read(folder / "dependabot.yml") or ""
    preset["ci_steps_yml"] = read(folder / "ci-steps.yml") or ""
    return preset


def render_config(presets: list[dict]) -> tuple[str, str]:
    """The CHECKS and EDIT_LINTERS lines for verify.py's configuration block."""
    checks = [tuple(c) for p in presets for c in p["checks"]]
    linters = {ext: cmd for p in presets for ext, cmd in p["edit_linters"].items()}
    checks_src = CHECKS_LINE if not checks else (
        "CHECKS: list[tuple[str, str, str, list[str]]] = [\n"
        + "".join(f"    ({', '.join(json.dumps(x) for x in c)}),\n" for c in checks) + "]\n")
    linters_src = LINTERS_LINE if not linters else (
        "EDIT_LINTERS: dict[str, list[str]] = {\n"
        + "".join(f"    {json.dumps(ext)}: {json.dumps(cmd)},\n" for ext, cmd in linters.items()) + "}\n")
    return checks_src, linters_src


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one '{old.strip()}' to replace")
    write(path, text.replace(old, new))


def new(dest: Path, name: str, scopes: list[str], stacks: list[str]) -> int:
    unknown = sorted(set(stacks) - set(available_stacks()))
    if unknown:
        print(f"unknown stack(s): {', '.join(unknown)}; available: {', '.join(available_stacks())}", file=sys.stderr)
        return 1
    if dest.exists() and any(dest.iterdir()):
        print(f"{dest} is not empty; use `sync` for an existing repo", file=sys.stderr)
        return 1
    shutil.copytree(TEMPLATE, dest, dirs_exist_ok=True)
    presets = [load_preset(s) for s in stacks]

    scope_list = ", ".join(f"`{s}`" for s in scopes) or "`core`"
    replace_once(dest / AGENTS, "{{SCOPES}}", scope_list)
    replace_once(dest / AGENTS, "# Engineering Standards", f"# {name}: Engineering Standards")
    checks_src, linters_src = render_config(presets)
    replace_once(dest / VERIFY, CHECKS_LINE, checks_src)
    replace_once(dest / VERIFY, LINTERS_LINE, linters_src)
    replace_once(dest / ".github/workflows/ci.yml", CI_MARKER, "\n".join(p["ci_steps_yml"] for p in presets))
    replace_once(dest / ".github/dependabot.yml", DEPENDABOT_MARKER, "\n".join(p["dependabot_yml"] for p in presets))
    ignore = [line for p in presets for line in p["gitignore"]]
    if ignore:
        write(dest / ".gitignore", read(dest / ".gitignore") + "\n".join(ignore) + "\n")
    write_stamp(dest, stacks)

    # Link the shared skills into every SKILL_MIRRORS folder (.claude/skills, ...).
    linked = subprocess.run([sys.executable, str(dest / VERIFY), "--only", "skills", "--fix"])
    print(f"\nCreated {dest} (standards {VERSION}, stacks: {', '.join(stacks) or 'none'}). Next:")
    print("  1. git init && git add -A && git commit -m \"chore: start from agent standards\"")
    print("     then: bash scripts/setup-hooks.sh (after the first commit: the hook caps commits at 5 files)")
    print("  2. Fill in the TODOs in AGENTS.md (sections 6-8) and .agents/skills/review-change/SKILL.md")
    print("  3. Adjust CHECKS in scripts/verify.py and the CI install steps to the repo's real layout")
    return linked.returncode


# --- CLI ------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_new = sub.add_parser("new", help="create a repo from the template")
    p_new.add_argument("dest", type=Path)
    p_new.add_argument("--name", required=True)
    p_new.add_argument("--stack", default="", help="comma-separated stacks, see `stacks`")
    p_new.add_argument("--scopes", default="", help="comma-separated commit scopes, e.g. core,api,web")
    p_check = sub.add_parser("check", help="report where repos differ from the template")
    p_check.add_argument("repos", nargs="*", type=Path)
    p_check.add_argument("--diff", action="store_true")
    p_sync = sub.add_parser("sync", help="rewrite the shared parts of repos from the template")
    p_sync.add_argument("repos", nargs="*", type=Path)
    sub.add_parser("stacks", help="list the available stacks")
    args = parser.parse_args()

    def items(text: str) -> list[str]:
        return [s.strip() for s in text.split(",") if s.strip()]

    if args.command == "stacks":
        for stack in available_stacks():
            print(f"{stack:10} {load_preset(stack)['description']}")
        return 0
    if args.command == "new":
        return new(args.dest, args.name, items(args.scopes), items(args.stack))

    repos = [r.resolve() for r in args.repos] or discover()
    if not repos:
        print(f"no repos given and none with {STAMP} found", file=sys.stderr)
        return 1
    failed = False
    for repo in repos:
        if args.command == "sync":
            print(f"== {repo.name}")
            sync(repo)
            continue
        problems = drift(repo, args.diff)
        print(f"== {repo.name}: {'in line with ' + VERSION if not problems else f'{len(problems)} difference(s)'}")
        for problem in problems:
            print(f"   {problem}")
        failed |= bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
