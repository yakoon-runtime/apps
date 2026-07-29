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

### Share via GitHub Releases

Before publishing, create a fine-grained personal access token:

1. Go to https://github.com/settings/personal-access-tokens
2. Create a new token:
   - Repository access: `yakoon-runtime/apps`
   - Permissions: Contents → **Read & Write**
3. Set it in your environment:

```bash
export YAK_GITHUB_TOKEN=github_pat_xxxxxxxxxxxxxxxxx
# Add to ~/.bashrc or ~/.zshrc for persistence
```

Then publish:

```bash
# Publisher:
yak build hello
yak publish y5n-packs-hello --repository github:yakoon-runtime/apps --release
# → published at https://github.com/yakoon-runtime/apps/releases

# Consumer:
mkdir other && cd other
yak init
yak install y5n-packs-hello --repository github:yakoon-runtime/apps
yak sync
yak shell
```

### Share via local filesystem

```bash
yak build hello
yak publish y5n-packs-hello             # → ~/.yak/artifacts/

# Another developer on the same machine:
mkdir other && cd other
yak init
yak install y5n-packs-hello             # finds it from ~/.yak/artifacts/
yak sync
yak shell
```

## Artifact lifecycle

```
create → build → publish → install → sync → shell
```

| Step | Command | Effect |
|------|---------|--------|
| 1 | `yak create pack <name>` | Scaffolds a new pack project |
| 2 | `yak build <source>` | Builds wheel + artifact.yml → `.yak/artifacts/` |
| 3 | `yak publish <name>` | Copies artifact → `~/.yak/artifacts/` (shareable) |
| 4 | `yak install <name>` | Installs wheel → `.venv` + `.yak/state.toml` |
| 5 | `yak sync` | Reconciles environment → `.yak/environment.yml` + workspace |
| 6 | `yak shell` | Opens interactive shell |

## Architecture

Every `yak` command starts by locating a **YakContext** — similar to a
Git repository, it defines the root for builds, artifacts, environments,
and the workspace. Commands find it by walking up from the current
working directory.

```
YakContext
    │
    ▼
Template (desired state)
    │
    ▼
Environment (instance)
    │
    ▼
Workspace (materialized)
    │
    ▼
Runtime
```

| Layer | Location | Created by |
|-------|----------|------------|
| **YakContext** | `<root>/.yak/` | `yak init` |
| **Context marker** | `.yak/context.toml` | `yak init` |
| **Environment** | `.yak/environment.yml` | `install` / `bootstrap` / `sync` |
| **Installation state** | `.yak/state.toml` | `install` |
| **Build artifacts** | `.yak/artifacts/` | `build` |

## Language-neutral artifacts

Yakoon artifacts are independent of the implementation language.
A single artifact may contain:

- Python wheels (`.whl`)
- .NET assemblies (`.dll`)
- Java archives (`.jar`)
- Native binaries
- WebAssembly modules

The `artifact.yml` manifest describes the builder, host, and fingerprint —
the runtime installs and materializes artifacts without depending on a
specific programming language.

## Commands

```
  Getting started
    init                   Create a Yak context

  Development
    create pack            Create a new pack
    create command         Add a command to the current pack
    bootstrap              Prepare this repository for development

  Packaging
    build                  Build artifacts
    publish                Publish an artifact to ~/.yak/artifacts/

  Environment
    install                Install a pack
    sync                   Sync workspace with environment

  Run
    shell                  Open the Yakoon shell
    runtime                Manage the runtime service
    web                    Manage the web service

  Tools
    status                 Show installation status
    resolve                Show resolved artifacts
    logs                   Show logs
    doctor                 Check installation health
```

## Context model

```bash
yak init                    #  .yak/context.toml
yak create pack hello       #  hello/pack.toml + structure/
yak build hello             #  → .yak/artifacts/
yak publish y5n-packs-hello #  → ~/.yak/artifacts/ (shareable)
yak install y5n-packs-hello #  → .venv + .yak/state.toml
yak sync                    #  → .yak/environment.yml + workspace
yak shell                   #  → interactive shell
```

- `init` and `install` create context markers.
- All other commands find the context via `find_context_root()`.
- No global state — each context is self‑contained.

## Context roots

The `.yak/context.toml` created by `yak init` can declare **roots** —
directories where `yak` searches for packs, runtime, apps, and SDK
components. Roots can point to any directory layout.

> **The repository layout is a development concern, not a platform concern.**

### Monorepo (default)

```toml
[context]
name = "yakoon"

[roots]
dirs = ["packs", "runtime", "apps", "sdk"]
```

`yak init` detects these directories automatically.

### Standalone pack repository

A product in its own repository:

```toml
[context]
name = "crm"

[roots]
dirs = ["."]
```

Packages are discovered directly in the repository root.

### Workspace with multiple repositories

```toml
[context]
name = "workspace"

[roots]
dirs = [
    "../yakoon/runtime",
    "../yakoon/sdk",
    "../crm",
    "../luma",
]
```

Roots are resolved relative to the context directory. Any directory
containing a `pack.toml`, `pyproject.toml`, or known structure will
be discovered automatically.

> **Yakoon distinguishes between source repositories and artifact repositories.**
> Source code may live anywhere — in a monorepo, in product-specific repos,
> or in a workspace combining multiple repos. The platform only consumes
> published artifacts. The repository layout is invisible to the runtime.

### How roots are used

```
CLI
 │
 ▼
Context.current()
 │
 ▼
context.resolve_roots()    → [./packs, ./runtime, ./apps, ...]
 │
 ▼
FileRepository(*roots)     → finds pack.toml, resolves distributions
DirectoryArtifactStore(*roots) → finds artifacts, resolves mounts
```

There is no architectural difference between "core" and "product"
components. The only difference is which roots the context provides.
