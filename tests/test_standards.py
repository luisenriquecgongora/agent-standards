"""standards.py: new repos work, check finds drift, sync repairs only the shared parts."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import standards  # noqa: E402


def run(*args, cwd=HERE, stdin=None):
    return subprocess.run([sys.executable, *map(str, args)], cwd=cwd, input=stdin,
                          capture_output=True, text=True)


def new_repo(tmp_path, stacks=""):
    dest = tmp_path / "demo"
    result = run("standards.py", "new", dest, "--name", "demo", "--stack", stacks, "--scopes", "api")
    assert result.returncode == 0, result.stderr
    return dest


def test_new_repo_without_stack_passes_its_own_verify(tmp_path):
    dest = new_repo(tmp_path)
    assert run(dest / "scripts/verify.py").returncode == 0
    assert (dest / ".claude/skills/review-change/SKILL.md").is_file()
    assert "[`api`, `config`" in (dest / "AGENTS.md").read_text(encoding="utf-8")
    assert run("standards.py", "check", dest).returncode == 0


@pytest.mark.parametrize("stack", standards.available_stacks())
def test_every_stack_renders_valid_files(tmp_path, stack):
    yaml = pytest.importorskip("yaml")
    dest = new_repo(tmp_path, stack)
    preset = standards.load_preset(stack)
    verify = (dest / "scripts/verify.py").read_text(encoding="utf-8")
    for check in preset["checks"]:
        assert json.dumps(check[1]) in verify
    compile(verify, "verify.py", "exec")
    ci = yaml.safe_load((dest / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert ci["jobs"]["verify"]["steps"][-1]["name"] == "Verify"
    deps = yaml.safe_load((dest / ".github/dependabot.yml").read_text(encoding="utf-8"))
    assert len(deps["updates"]) == 2
    assert json.loads((dest / ".agent-standards").read_text())["stacks"] == [stack]
    assert run(dest / "scripts/verify.py", "--only", "skills").returncode == 0
    assert run("standards.py", "check", dest).returncode == 0


def test_unknown_stack_is_refused(tmp_path):
    result = run("standards.py", "new", tmp_path / "x", "--name", "x", "--stack", "cobol")
    assert result.returncode == 1 and "unknown stack" in result.stderr


def test_sync_repairs_shared_parts_and_keeps_repo_parts(tmp_path):
    dest = new_repo(tmp_path, "python")
    verify = dest / "scripts/verify.py"
    agents = dest / "AGENTS.md"
    v = verify.read_text(encoding="utf-8")
    verify.write_text(v.replace("def resolve(", "def resolve_edited(").replace('"-q"]', '"-x"]'), encoding="utf-8")
    a = agents.read_text(encoding="utf-8")
    agents.write_text(a.replace("Leave untouched code exactly as it is.", "Whatever.")
                       .replace("- Install: `TODO`", "- Install: `make`"), encoding="utf-8")
    (dest / "CLAUDE.md").write_text("changed\n", encoding="utf-8")

    check = run("standards.py", "check", dest)
    assert check.returncode == 1 and "3 difference(s)" in check.stdout

    assert run("standards.py", "sync", dest).returncode == 0
    assert run("standards.py", "check", dest).returncode == 0
    v2, a2 = verify.read_text(encoding="utf-8"), agents.read_text(encoding="utf-8")
    assert "def resolve(" in v2 and '"-x"]' in v2           # shared body restored, repo config kept
    assert "exactly as it is" in a2 and "`make`" in a2       # shared section restored, repo section kept


def test_old_stamp_is_reported_and_sync_shows_changes(tmp_path):
    dest = new_repo(tmp_path)
    (dest / ".agent-standards").write_text('{"version": "1.0.0", "stacks": []}', encoding="utf-8")
    check = run("standards.py", "check", dest)
    assert f"on 1.0.0, template is {standards.VERSION}" in check.stdout
    synced = run("standards.py", "sync", dest)
    assert f"1.0.0 -> {standards.VERSION}" in synced.stdout and "## 1.0.0" not in synced.stdout
    assert json.loads((dest / ".agent-standards").read_text())["version"] == standards.VERSION


def test_discover_finds_stamped_repos(tmp_path, monkeypatch):
    for name in ("a", "group/b"):
        (tmp_path / name).mkdir(parents=True)
        (tmp_path / name / ".agent-standards").write_text("{}", encoding="utf-8")
    (tmp_path / "unmanaged").mkdir()
    monkeypatch.setitem(standards.CONFIG, "discover", {"root": str(tmp_path), "max_depth": 2})
    assert [p.name for p in standards.discover()] == ["a", "b"]


def test_edit_lint_hook_runs_configured_linter(tmp_path):
    dest = new_repo(tmp_path)
    verify = dest / "scripts/verify.py"
    v = verify.read_text(encoding="utf-8")
    linter = '{".txt": ["{py}", "-c", "import sys; print(\\"bad\\", sys.argv[1]); sys.exit(1)", "{file}"]}'
    empty = "EDIT_LINTERS: dict[str, list[str]] = {}"
    verify.write_text(v.replace(empty, empty[:-2] + linter), encoding="utf-8")
    hook = dest / ".claude/hooks/lint_edited.py"
    (dest / "notes.txt").write_text("x", encoding="utf-8")
    (dest / "other.md").write_text("x", encoding="utf-8")

    flagged = run(hook, stdin=json.dumps({"tool_input": {"file_path": str(dest / "notes.txt")}}))
    assert flagged.returncode == 2 and "bad" in flagged.stderr
    ignored = run(hook, stdin=json.dumps({"tool_input": {"file_path": str(dest / "other.md")}}))
    assert ignored.returncode == 0


def test_example_matches_what_new_generates(tmp_path):
    """examples/my-app is regenerated with: python standards.py new examples/my-app --name my-app
    --stack python,node --scopes api,web (delete the folder first)."""
    example = HERE / "examples" / "my-app"
    fresh = tmp_path / "my-app"
    assert run("standards.py", "new", fresh, "--name", "my-app", "--stack", "python,node",
               "--scopes", "api,web").returncode == 0

    def files(root):
        return {p.relative_to(root).as_posix(): p for p in root.rglob("*")
                if (p.is_file() or p.is_symlink()) and "__pycache__" not in p.parts}

    want, have = files(fresh), files(example)
    assert sorted(have) == sorted(want), "example is stale: regenerate it (see docstring)"
    for rel, path in want.items():
        if path.is_symlink():
            assert have[rel].is_symlink()
        else:
            assert have[rel].read_bytes().replace(b"\r\n", b"\n") == path.read_bytes(), f"{rel} is stale"


def test_bad_verify_python_gives_a_clear_message(tmp_path):
    dest = new_repo(tmp_path)
    env = {**os.environ, "VERIFY_PYTHON": str(tmp_path / "no-such-python")}
    result = subprocess.run([sys.executable, str(dest / "scripts/verify.py")], capture_output=True, text=True,
                            env=env, check=False)
    assert result.returncode == 1
    assert "VERIFY_PYTHON is set to" in result.stderr and "Traceback" not in result.stderr

    hook = subprocess.run([sys.executable, str(dest / ".claude/hooks/lint_edited.py")], capture_output=True,
                          text=True, env=env, check=False,
                          input=json.dumps({"tool_input": {"file_path": str(dest / "scripts/verify.py")}}))
    assert hook.returncode == 0 and "Traceback" not in hook.stderr


def test_sync_adds_a_missing_shared_section(tmp_path):
    dest = new_repo(tmp_path)
    agents = dest / "AGENTS.md"
    full = agents.read_text(encoding="utf-8")
    section_11 = standards.agents_sections(full)["11"]
    without = full.replace(section_11, "").rstrip("\n") + "\n"
    without = without.replace(standards.agents_sections(full)["2"], "")  # a middle section too
    agents.write_text(without, encoding="utf-8")
    assert run("standards.py", "check", dest).returncode == 1

    assert run("standards.py", "sync", dest).returncode == 0
    assert agents.read_text(encoding="utf-8") == full
    assert run("standards.py", "check", dest).returncode == 0
