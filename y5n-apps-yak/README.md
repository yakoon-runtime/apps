# yak — Yakoon CLI

`yak` is the command-line interface for Yakoon — a composable,
language‑neutral runtime platform.

## Typical workflow

```
create → build → publish → install → sync → shell
```

## Quick start

### Local development

```bash
mkdir demo && cd demo
yak init                    # Create a Yak context
yak create pack hello       # Scaffold a new pack
cd hello
yak create command greet    # Add a command to the pack
cd ..
yak build hello             # Build the pack
yak install y5n-packs-hello # Install the artifact
yak sync                    # Sync environment + materialize workspace
yak shell                   # Open the interactive shell
```

### Share with others

```bash
yak build hello             # Build the pack
yak publish y5n-packs-hello # Publish to ~/.yak/artifacts/
# Other developer:
mkdir other && cd other
yak init
yak install y5n-packs-hello # Finds it from ~/.yak/artifacts/
yak sync
yak shell
```

## Architecture

Every `yak` command starts by locating a **YakContext**. The context is the
central workspace for all Yakoon operations — a directory containing `.yak/`.

```
Template → Environment (Desired State) → Workspace (Materialized) → Runtime
```

| Layer | Location | Created by |
|-------|----------|------------|
| **YakContext** | `<root>/.yak/` | `yak init` |
| **Context marker** | `.yak/context.toml` | `yak init` |
| **Environment** | `.yak/environment.yml` | `install` / `bootstrap` / `sync` |
| **Installation state** | `.yak/state.toml` | `install` |
| **Build artifacts** | `.yak/artifacts/` | `build` |

## Commands

```
  Getting started
    init                   Create a Yak context

  Development
    create pack            Create a new pack
    create command         Add a command to the current pack

  Build
    build                  Build artifacts
    bootstrap              Prepare this repository for development

  Install
    install                Install a pack
    sync                   Sync workspace with environment

  Run
    shell                  Open the Yakoon shell
    runtime                Manage the runtime service
    web                    Manage the web service

  Tools
    status                 Show installation status
    publish                Publish an artifact to ~/.yak/artifacts/
    resolve                Show resolved artifacts
    logs                   Show logs
    doctor                 Check installation health
```

## Artifact lifecycle

```
create → build → publish → install → sync → shell
```

| Step | Command | Effect |
|------|---------|--------|
| 1 | `yak create pack <name>` | Scaffolds a new pack project |
| 2 | `yak build <source>` | Builds wheel + artifact.yml → `.yak/artifacts/` |
| 3 | `yak publish <name>` | Copies artifact → `~/.yak/artifacts/` |
| 4 | `yak install <name>` | Installs wheel → `.venv` + `.yak/state.toml` |
| 5 | `yak sync` | Reconciles environment → `.yak/environment.yml` + workspace |
| 6 | `yak shell` | Opens interactive shell |

## Context model (like Git)

```bash
yak init                    #  .yak/context.toml
yak create pack hello       #  hello/pack.toml + structure/
yak build hello             #  → .yak/artifacts/
yak publish y5n-packs-hello #  → ~/.yak/artifacts/
yak install y5n-packs-hello #  → .venv + .yak/state.toml
yak sync                    #  → .yak/environment.yml + workspace
yak shell                   #  → interactive shell
```

- `init` and `install` create context markers.
- All other commands find the context via `find_context_root()`.
- No global state — each context is self‑contained.
- Artifacts are language‑neutral: works with .whl, .dll, .jar, etc.
