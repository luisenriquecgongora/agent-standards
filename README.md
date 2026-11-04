# agent-standards

A **base configuration** for software repos, so that people and coding agents (Claude Code, Codex, OpenCode,
Cursor, Copilot, Antigravity, ...) work in every repo the same way, and can prove when work is finished.
It creates new repos with that configuration in one command, and keeps existing repos up to date with it.

## Start here

| You want to... | Read |
| :--- | :--- |
| Work in a repo that already uses this (most people) | [docs/using-a-repo.md](docs/using-a-repo.md) |
| Start a new project | [docs/new-project.md](docs/new-project.md) |
| Change the rules for every repo, add a language or a coding agent | [docs/maintaining.md](docs/maintaining.md) |
| Look something up: commands, files, settings | [docs/reference.md](docs/reference.md) |
| Understand a term | [docs/glossary.md](docs/glossary.md) |

## Why this exists

Coding agents do good work when a repo tells them the rules and lets them check their own work. Without a
shared setup, every repo is different, and the agent (or a new team member) has to guess:

| Without it | With it |
| :--- | :--- |
| Each agent reads its own instruction file; the rules drift apart or are missing | One `AGENTS.md` that every agent reads |
| "Done" means "I think it works"; failures show up later in CI | One command, `verify.py`, runs exactly what CI runs: if it passes on your machine, it passes in CI |
| Lint errors pile up until someone notices | The agent is told about a lint error the moment it edits a file, and fixes it right away |
| Huge commits with vague messages, hard to review or undo | Small commits in a fixed format, each one working on its own |
| Recurring tasks are explained again every time | Skills: step-by-step playbooks any agent can follow |
| Agents change code faster than people can read it; nobody can say what changed or why | Every repo keeps `docs/ARCHITECTURE.md`, a colored map of its parts, current, and every pull request explains what, why and how it was verified, with a diagram when a flow changed |
| Every new project repeats the setup; fixes are copied by hand into each repo | `new` sets a project up in one command; `sync` sends a fix to every repo |

The setup does not make agents smarter. It makes their work **checkable and consistent**, which is what lets you
hand them more: you write the task, the agent does it under the repo's rules and proves it with `verify.py`, and
you review small, clear commits.

### How an agent works in a repo set up this way

```mermaid
flowchart TD
    task["Task<br/>(task form in .github/ISSUE_TEMPLATE)"] --> agent["Any coding agent"]
    agents["AGENTS.md<br/>rules, repo map, commands"] -.->|read first| agent
    skills[".agents/skills/<br/>playbooks for recurring tasks"] -.->|read when it matches| agent
    agent --> edit["Edits code"]
    edit --> lint{"Lint-on-edit hook"}
    lint -->|problem found| edit
    lint -->|clean| verify{"scripts/verify.py<br/>same checks as CI"}
    verify -->|fails| edit
    verify -->|passes| commit{"Commit hooks<br/>message format, max 5 files"}
    commit -->|rejected| edit
    commit -->|accepted| pr["Pull request<br/>(PR template)"]
    pr --> ci{"CI<br/>verify.py, secret scan, commit messages"}
    ci -->|fails| edit
    ci -->|passes| review["You review and merge"]

    classDef input fill:#ede9fe,stroke:#7c3aed,color:#3b0764
    classDef work fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef gate fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d
    class task,agents,skills input
    class agent,edit,pr work
    class lint,verify,commit,ci gate
    class review done
    linkStyle 5,7,9,12 stroke:#dc2626,color:#dc2626
```

🟪 what the agent reads · 🟦 the work · 🟨 automatic checks · 🟩 finished · red arrows: a check failed, back to work

Every failed check sends the work back to the agent, so most problems are fixed before a person sees them.

### How agent-standards keeps repos in line

```mermaid
flowchart LR
    subgraph std["agent-standards (this repo)"]
        template["template/<br/>base files"]
        presets["presets/<br/>python, node, rust, ..."]
        config["standards.json<br/>what is shared"]
        changelog["CHANGELOG.md<br/>what changed per version"]
    end
    template --> new(["standards.py new"])
    presets --> new
    new --> fresh["New repo<br/>base configuration + stamp"]
    config --> sync(["standards.py sync"])
    template --> sync
    changelog --> sync
    sync -->|rewrites only the shared parts| r1["Existing repo A"]
    sync --> r2["Existing repo B"]
    sync --> r3["..."]
    check(["standards.py check"]) -.->|reports drift, changes nothing| r1
    check -.-> r2
    check -.-> r3

    classDef source fill:#ede9fe,stroke:#7c3aed,color:#3b0764
    classDef tool fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef repo fill:#dcfce7,stroke:#16a34a,color:#14532d
    class template,presets,config,changelog source
    class new,sync,check tool
    class fresh,r1,r2,r3 repo
    style std fill:#faf5ff,stroke:#7c3aed
```

🟪 the source of the standards · 🟦 the commands · 🟩 your repos

Each repo's configuration has two layers:

- **Shared base**: the rules every repo has in common (commit rules, how `verify.py` works, the agent
  instructions that apply everywhere). Changed only here, and sent to every repo with `sync`.
- **The repo's own configuration**: its checks, commit scopes, repo map, CI install steps and skills. The repo
  changes these freely; `sync` never touches them.

```mermaid
flowchart TB
    subgraph repo["📁 any managed repo"]
        direction TB
        subgraph base["🟪 Shared base: identical in every repo, updated by sync"]
            direction LR
            b1["CLAUDE.md"]
            b2["AGENTS.md<br/>sections 1, 2, 4, 10, 11"]
            b3["verify.py<br/>the engine"]
            b4["commit hooks<br/>lint hook"]
        end
        subgraph own["🟩 The repo's own configuration: yours to change, sync never touches it"]
            direction LR
            o1["AGENTS.md<br/>scopes, map, commands, gotchas"]
            o2["verify.py<br/>CHECKS: what to run"]
            o3["skills<br/>.agents/skills/"]
            o4["CI install steps<br/>Dependabot, templates"]
        end
        base ~~~ own
    end
    std["🟦 agent-standards"] -->|sync| base

    classDef shared fill:#ede9fe,stroke:#7c3aed,color:#3b0764
    classDef owned fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef tool fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    class b1,b2,b3,b4 shared
    class o1,o2,o3,o4 owned
    class std tool
    style base fill:#faf5ff,stroke:#7c3aed
    style own fill:#f0fdf4,stroke:#16a34a
    style repo fill:#ffffff,stroke:#9ca3af
```

Some files have a part in each layer: in `AGENTS.md` four sections are shared and the rest are the repo's; in
`verify.py` the program is shared and its configuration block (`CHECKS`, ...) is the repo's.
The full list is in [docs/reference.md](docs/reference.md#what-is-shared-and-what-each-repo-owns).

## Where to put it, and where to run it

`agent-standards` can live anywhere, and works on **one repo or a whole folder of repos**. Like git, it looks at
**the folder you run it in**:

| You run `check` or `sync` in... | It manages |
| :--- | :--- |
| A folder of repos (`~/projects/`) | Every managed repo in it, up to two folder levels down |
| A managed repo, or any folder inside it (`my-api/src/`) | That repo |
| A repo that is also a workspace (it has its own stamp and managed repos inside it) | That repo and the managed repos inside it |
| The `agent-standards` folder itself | The repos in the folder that holds it |

A repo is **managed** when it has an `.agent-standards` file at its root (see the next section). Folders without
one are ignored. To start from another folder, add `--root <folder>`; to pick repos yourself, name them:
`python standards.py check ~/code/my-api ~/work/my-web`.

```mermaid
flowchart TD
    run["You run: python standards.py check<br/>in some folder"] --> up{"Is this folder, or a folder above it,<br/>a repo with .agent-standards?"}
    up -->|yes| one["➕ that repo"]
    up -->|no| down
    one --> down{"Repos with .agent-standards<br/>up to 2 levels below?"}
    down -->|yes| many["➕ each of them"]
    down -->|no| result
    many --> result["check / sync those repos"]

    classDef start fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef gate fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef found fill:#dcfce7,stroke:#16a34a,color:#14532d
    class run,result start
    class up,down gate
    class one,many found
```

### Layout 1: a folder of repos

The usual setup: clone `agent-standards` next to your repos and run it there.

```mermaid
flowchart TD
    ws["📁 ~/projects/<br/>your workspace folder"]
    ws --> std["📁 agent-standards/<br/>this repo: the tool"]
    ws --> api["📁 my-api/<br/>a repo"]
    ws --> web["📁 my-web/<br/>a repo"]
    ws --> clients["📁 clients/<br/>a plain folder, not a repo"]
    ws --> other["📁 some-other-repo/<br/>a repo"]
    clients --> sdk["📁 my-sdk/<br/>a repo"]
    api --> s1["📄 .agent-standards"]
    api --> src["📁 src/, tests/, docs/ ...<br/>no stamp in here"]
    web --> s2["📄 .agent-standards"]
    sdk --> s3["📄 .agent-standards"]
    other --> none["no .agent-standards file"]

    classDef tool fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef managed fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef stamp fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef plain fill:#f3f4f6,stroke:#9ca3af,color:#374151
    classDef ignored fill:#f3f4f6,stroke:#9ca3af,color:#6b7280,stroke-dasharray:4 3
    class std tool
    class api,web,sdk managed
    class s1,s2,s3 stamp
    class ws,clients,src plain
    class other,none ignored
```

| Color | Meaning |
| :--- | :--- |
| 🟦 Blue | `agent-standards`, the tool |
| 🟩 Green | A **managed** repo: it has a stamp file at its root |
| 🟨 Yellow | The stamp file, `.agent-standards`: **one per repo, at the repo's root** |
| ⬜ Grey | Plain folders, and folders inside a repo: never have a stamp |
| ⬜ Grey, dashed | A repo without a stamp: `check` and `sync` ignore it |

```bash
cd ~/projects
git clone git@github.com:luisenriquecgongora/agent-standards.git
# or: git clone https://github.com/luisenriquecgongora/agent-standards.git
python agent-standards/standards.py check            # all managed repos in ~/projects
```

### Layout 2: one repo

Keep `agent-standards` anywhere (your home folder, a tools folder, or even inside the repo, e.g.
`my-api/tools/agent-standards/`) and run it from inside the repo:

```mermaid
flowchart LR
    subgraph repo["📁 my-api/ · a managed repo"]
        direction TB
        s["📄 .agent-standards"]
        src["📁 src/ · tests/ · docs/"]
        tool["📁 tools/agent-standards/<br/>optional: the tool can live here too"]
    end
    you["you, in my-api/ or my-api/src/"] -->|python tools/agent-standards/standards.py check| repo

    classDef tool fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef stamp fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef plain fill:#f3f4f6,stroke:#9ca3af,color:#374151
    class tool,you tool
    class s stamp
    class src plain
    style repo fill:#f0fdf4,stroke:#16a34a
```

```bash
cd ~/code/my-api
python ~/tools/agent-standards/standards.py check    # just my-api
```

The tool never treats itself or its `examples/` as a repo to manage, wherever it lives.

## The `.agent-standards` file

Every managed repo has **exactly one** `.agent-standards` file, at its root, next to `AGENTS.md`. Folders
inside the repo (`src/`, `packages/api/`, ...) never have one, even in a monorepo with many packages. It looks
like this:

```json
{
  "version": "1.1.1",
  "stacks": ["node", "python"]
}
```

| Field | Means | Written by |
| :--- | :--- | :--- |
| `version` | Which release of the standards this repo has | `new`, then `sync` every time it updates the repo |
| `stacks` | Which languages the repo uses | `new` (from `--stack`); you, for a repo brought in later |

It has two jobs: it **marks** the repo as managed, so `check` and `sync` find it, and it **records the version**,
so they know what the repo is missing:

```mermaid
flowchart LR
    stamp["📄 my-api/.agent-standards<br/>version 1.1.0"] --> check{"standards.py check<br/>template is 1.1.1"}
    check -->|same version, files match| ok["✅ in line with 1.1.1"]
    check -->|older version or edited files| behind["⚠️ reports the differences"]
    behind --> sync["standards.py sync"]
    sync --> updated["shared files updated,<br/>changelog 1.1.0 → 1.1.1 printed,<br/>stamp set to 1.1.1"]

    classDef stamp fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef tool fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef good fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef warn fill:#ffedd5,stroke:#ea580c,color:#7c2d12
    class stamp stamp
    class check,sync tool
    class ok,updated good
    class behind warn
```

Do not edit `version` by hand: `sync` sets it after updating the files, so it always matches what the repo
really has.

## Quick start

Needs Python 3.10+, git and bash (Git Bash on Windows). Full steps in [docs/new-project.md](docs/new-project.md).

```bash
cd ~/projects/agent-standards
python standards.py new ../my-app --name my-app --stack python,node --scopes api,web
cd ../my-app
git init -b main && git add -A && git commit -m "chore: start from agent standards"
bash scripts/setup-hooks.sh
python scripts/verify.py
```

See what that creates in [`examples/my-app/`](examples/my-app/), the exact output of the `new` command above,
kept current by a test. (Its `.github/` files are inactive there: GitHub only runs workflows at a repo's root.)

Keep repos up to date:

```bash
python standards.py check     # which repos differ from the template (changes nothing)
python standards.py sync      # update their shared parts; review with git diff, then commit in each repo
```
