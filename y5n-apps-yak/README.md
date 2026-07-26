# yak — Yakoon Platform Manager

`yak` is the command-line interface for managing Yakoon — a composable,
language‑neutral runtime platform.

## Quick start

```bash
mkdir demo && cd demo
yak init                    # Create a Yak context
yak install dev             # Install the developer distribution
yak shell                   # Open the interactive shell
```

## Architecture

Every `yak` command starts by locating a **YakContext**. The context is the
central workspace for all Yakoon operations — a directory containing `.yak/`
(context.toml or state.toml). Commands find it automatically by walking up
from the current working directory.

```
             YakContext
                  │
      ┌───────────┼────────────┐
      │           │            │
      ▼           ▼            ▼
   Sources    Artifacts   Installations
      │           ▲
      │           │
      └── build ──┘
                  │
          ┌───────┴────────┐
          ▼                ▼
       publish         install
```

`build` reads from **Sources** and writes **Artifacts** into the context.
`publish` and `install` read from **Artifacts** within the same context.

| Layer | Location | Created by |
|-------|----------|------------|
| **YakContext** | `<root>/.yak/` | `yak init` |
| **Context marker** | `.yak/context.toml` | `yak init` |
| **Installation state** | `.yak/state.toml` | `yak install` |
| **Build artifacts** | `.yak/artifacts/` | `yak build` |

## Commands

```
  Getting started
    init  [dir]     Create a Yak context

  Development
    build [source]  Build artifacts from source into the current context
    bootstrap       Prepare this repository for development
    workspace create <name>  Create a new workspace
    resolve <name>  Show resolved artifacts

  Management
    install <name>  Install a distribution
    update          Update the current installation
    status          Show installation status
    doctor          Check installation health

  Services
    runtime <act>   Manage the runtime service
    web     <act>   Manage the web service
    shell           Open the Yakoon shell
```

## Context model (like Git)

```bash
yak init                    #  .yak/context.toml
yak install dev             #  .venv + .yak/state.toml
yak build ../project        #  → .yak/artifacts/
yak status                  #  ← .yak/state.toml (auto‑detected)
yak update                  #  re‑installs from cache
```

- `init` and `install` create context markers.
- All other commands find the context via `find_context_root()`.
- No global state — each context is self‑contained.
