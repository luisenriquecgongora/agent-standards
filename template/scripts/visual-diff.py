#!/usr/bin/env python3
"""
visual-diff.py - Fast Visual Change & Architecture Delta Generator.
Part of the agent-standards ecosystem.

Analyzes git diffs (staged by default, or against HEAD/revisions) and generates:
  1. A colored Mermaid diagram conforming to docs/ARCHITECTURE.md standards.
  2. A clean terminal-ready ASCII flow box for commit bodies and git logs.
  3. An interactive standalone HTML inspection dashboard opened directly in Chrome/Firefox.

Usage:
    python scripts/visual-diff.py                 # Mermaid output for staged changes
    python scripts/visual-diff.py --ascii         # ASCII box output for commit bodies
    python scripts/visual-diff.py --open          # Render and launch in browser
    python scripts/visual-diff.py --head          # Inspect last commit (HEAD~1..HEAD)
    python scripts/visual-diff.py --range main..  # Inspect branch against main
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get_git_changes(mode: str, revision_range: str | None = None) -> list[tuple[str, str, str | None]]:
    """Return list of (status, file_path, optional_old_path)."""
    cmd = ["git", "diff", "--name-status", "-M"]
    if revision_range:
        cmd.extend(revision_range.split())
    elif mode == "head":
        cmd.extend(["HEAD~1", "HEAD"])
    elif mode == "staged":
        cmd.append("--cached")
    elif mode == "unstaged":
        pass  # git diff --name-status
    elif mode == "auto":
        # Check staged first
        staged_res = subprocess.run(["git", "diff", "--cached", "--name-status", "-M"], capture_output=True, text=True)
        if staged_res.stdout.strip():
            return parse_git_status_output(staged_res.stdout)
        # Check working tree against HEAD
        wt_res = subprocess.run(["git", "diff", "HEAD", "--name-status", "-M"], capture_output=True, text=True)
        if wt_res.stdout.strip():
            return parse_git_status_output(wt_res.stdout)
        # Fallback to last commit
        cmd.extend(["HEAD~1", "HEAD"])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return []
    return parse_git_status_output(res.stdout)


def parse_git_status_output(output: str) -> list[tuple[str, str, str | None]]:
    changes = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status_code = parts[0][0].upper()
        if status_code == "R" and len(parts) >= 3:
            changes.append((status_code, parts[2], parts[1]))
        elif len(parts) >= 2:
            changes.append((status_code, parts[1], None))
    return changes


def classify_file(path_str: str) -> str:
    """Classify file into standard architecture category."""
    p = path_str.lower()
    if p.endswith((".md", ".txt", ".rst")) or p.startswith("docs/"):
        return "docs"
    if "test" in p or p.endswith((".spec.ts", ".spec.js", ".test.ts", ".test.js")):
        return "gate"
    if p.startswith(("scripts/", ".github/", ".claude/", ".agents/")) or p.endswith((".sh", ".bat", ".yml", ".yaml")):
        return "gate"
    if p.endswith((".json", ".toml", ".ini", ".env.example", ".editorconfig", ".gitattributes")):
        return "input"
    return "ours"


def sanitize_node_id(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", text).strip("_")


def generate_mermaid(changes: list[tuple[str, str, str | None]]) -> str:
    """Generate a Mermaid diagram matching the docs/ARCHITECTURE.md palette."""
    lines = [
        "```mermaid",
        "flowchart TD",
        "    subgraph Changeset[\"⚡ Visual Delta (Changeset)\"]",
    ]

    status_icons = {
        "A": "✨ Added",
        "M": "⚡ Modified",
        "D": "🗑️ Removed",
        "R": "↪️ Renamed",
    }

    # Group changes by high-level directory / module
    groups: dict[str, list[tuple[str, str, str | None]]] = {}
    for item in changes:
        status, file_path, _ = item
        parts = file_path.split("/")
        group_name = parts[0] if len(parts) > 1 else "root"
        groups.setdefault(group_name, []).append(item)

    node_classes = []
    node_counter = 0

    for group_name, items in groups.items():
        sub_id = sanitize_node_id(f"grp_{group_name}")
        lines.append(f'        subgraph {sub_id}["📁 {group_name}"]')
        for status, file_path, old_path in items:
            node_counter += 1
            node_id = f"node_{node_counter}_{sanitize_node_id(file_path)}"
            base_name = file_path.split("/")[-1]
            icon = status_icons.get(status, status)
            
            if status == "R" and old_path:
                label = f"{icon}: {old_path.split('/')[-1]} ➔ {base_name}"
            else:
                label = f"{icon}: {base_name}"
            
            lines.append(f'            {node_id}["{label}"]')

            if status == "D":
                node_classes.append(f"    class {node_id} risk")
            elif status == "A":
                node_classes.append(f"    class {node_id} done")
            else:
                cat = classify_file(file_path)
                node_classes.append(f"    class {node_id} {cat}")
        lines.append("        end")

    lines.append("    end")
    lines.extend(node_classes)

    # Architectural color palette
    lines.extend([
        "",
        "    classDef ours fill:#dbeafe,stroke:#2563eb,color:#1e3a8a",
        "    classDef input fill:#ede9fe,stroke:#7c3aed,color:#3b0764",
        "    classDef gate fill:#fef9c3,stroke:#ca8a04,color:#713f12",
        "    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d",
        "    classDef risk fill:#fee2e2,stroke:#dc2626,color:#7f1d1d",
        "```",
    ])
    return "\n".join(lines)


def generate_ascii(changes: list[tuple[str, str, str | None]]) -> str:
    """Generate a clean ASCII box flow diagram for commit bodies and terminal inspect."""
    if not changes:
        return "No changes detected."

    status_labels = {
        "A": "[+ Added]   ",
        "M": "[~ Modified]",
        "D": "[- Deleted] ",
        "R": "[> Renamed] ",
    }

    max_len = max(len(f"{status_labels.get(st, st)} {fp}") for st, fp, _ in changes)
    box_width = max(max_len + 4, 46)

    border_top = "┌" + "─" * (box_width - 2) + "┐"
    border_mid = "├" + "─" * (box_width - 2) + "┤"
    border_bot = "└" + "─" * (box_width - 2) + "┘"

    header_text = " Visual Delta & Impacted Flow"
    header_line = f"│{header_text}{' ' * (box_width - 2 - len(header_text))}│"

    lines = [border_top, header_line, border_mid]
    for st, fp, old_path in changes:
        tag = status_labels.get(st, f"[{st}]        ")
        item_text = f" {tag} {fp}"
        if len(item_text) > box_width - 3:
            item_text = item_text[: box_width - 6] + "..."
        lines.append(f"│{item_text}{' ' * (box_width - 2 - len(item_text))}│")

    lines.append(border_bot)
    return "\n".join(lines)


def open_visual_in_browser(mermaid_content: str, ascii_content: str, changes_count: int):
    """Generate standalone HTML preview and launch it in the browser."""
    script_opener = ROOT / "scripts" / "open-artifact.py"
    temp_dir = Path(tempfile.gettempdir())
    html_report = temp_dir / "visual_diff_inspection.md"

    md_content = f"""# Visual Change Inspection Report

**Total Changed Files:** {changes_count}  
Generated for fast human verification before committing or pushing.

---

## 📊 Visual Architecture Delta

{mermaid_content}

---

## 🖥️ Terminal Commit Representation

```text
{ascii_content}
```

> **Review Tip:** Verify that modifications are contained within expected module boundaries and do not exceed the 5-file atomic commit limit.
"""
    html_report.write_text(md_content, encoding="utf-8")

    if script_opener.exists():
        subprocess.run([sys.executable, str(script_opener), str(html_report), "chrome"])
    else:
        print(f"Report written to: {html_report}")


def main():
    parser = argparse.ArgumentParser(description="Fast Visual Change & Architecture Delta Generator.")
    parser.add_argument("--staged", action="store_true", help="Inspect staged changes (default if changes exist)")
    parser.add_argument("--head", action="store_true", help="Inspect last commit (HEAD~1..HEAD)")
    parser.add_argument("--range", help="Git revision range (e.g. main..HEAD)")
    parser.add_argument("--ascii", action="store_true", help="Output ASCII box representation for commit body")
    parser.add_argument("--mermaid", action="store_true", help="Output Mermaid diagram markdown")
    parser.add_argument("--open", "-o", action="store_true", help="Render interactive HTML dashboard and open in browser")
    parser.add_argument("--output", "-out", help="Write output to file")

    args = parser.parse_args()

    mode = "staged" if args.staged else ("head" if args.head else "auto")
    changes = get_git_changes(mode, args.range)

    if not changes:
        print("visual-diff: No changes detected to visualize.", file=sys.stderr)
        return

    mermaid_out = generate_mermaid(changes)
    ascii_out = generate_ascii(changes)

    if args.open:
        open_visual_in_browser(mermaid_out, ascii_out, len(changes))
        return

    output_text = ascii_out if args.ascii else mermaid_out

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Visual diff written to: {args.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
