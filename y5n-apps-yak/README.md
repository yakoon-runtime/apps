# yak — Yakoon CLI

`yak` is the command-line interface for Yakoon — a composable,
language‑neutral runtime platform.

## Typical workflow

```
Development:   create → build → publish
Installation:  install → add → update
Operation:     shell / runtime / status / doctor
```

## Quick start

### Local development

```bash
mkdir demo && cd demo
yak create pack hello       # Scaffold a new pack
cd hello
yak create command greet    # Add a command to the pack
cd ..
yak build hello             # Build the pack
yak install crm             # Create a Yakoon installation (interactive: 'yak install')
yak add y5n-packs-hello     # Add the built artifact to the installation
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
yak install crm
yak add y5n-packs-hello --repository github:yakoon-runtime/apps
yak shell
```

### Share via local filesystem

```bash
yak build hello
yak publish y5n-packs-hello             # → ~/.yak/artifacts/

# Another developer on the same machine:
mkdir other && cd other
yak install crm
yak add y5n-packs-hello                 # finds it from ~/.yak/artifacts/
yak shell
```

## Artifact lifecycle

```
create → build → publish
install → add → update
```

| Step | Command | Effect |
|------|---------|--------|
| 1 | `yak create pack <name>` | Scaffolds a new pack project |
| 2 | `yak build <source>` | Builds wheel + artifact.yml → `.yak/artifacts/` |
| 3 | `yak publish <name>` | Copies artifact → `~/.yak/artifacts/` (shareable) |
| 4 | `yak install <environment>` | Creates a Yakoon installation (workspace, deployment, state) |
| 5 | `yak add <component>` | Adds a distribution or artifact to the installation |
| 6 | `yak update` | Reconciles the installation with its desired state |
| 7 | `yak shell` | Opens interactive shell |

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

  Installation
    install                Create a Yakoon installation
    add                    Add a distribution or artifact
    update                 Update the installation
    sync                   Reconcile the workspace

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
yak install crm             #  → workspace + .yak/deployment.yml + state.toml
yak add y5n-packs-hello     #  → adds the artifact to the installation
yak shell                   #  → interactive shell
```

- `init` and `install` create context markers.
- All other commands find the context via `find_context_root()`.
- No global state — each context is self‑contained.

## Context sources

The `.yak/context.toml` created by `yak init` can declare **sources** —
directories where `yak` looks for packs, runtime, apps, and SDK source
code during development.

> **The repository layout is a development concern, not a platform concern.**
> Yakoon distinguishes between *source repositories* (where code lives)
> and *artifact repositories* (where published artifacts are consumed).

### Monorepo (default)

```toml
[context]
name = "yakoon"

[sources]
dirs = ["packs", "runtime", "apps", "sdk"]
```

`yak init` detects these directories automatically.

### Standalone product repository

```toml
[context]
name = "crm"

[sources]
dirs = ["."]
```

Packs are discovered directly in the repository root.

### Workspace with multiple repositories

```toml
[context]
name = "workspace"

[sources]
dirs = [
    "../yakoon/runtime",
    "../yakoon/sdk",
    "../crm",
    "../luma",
]
```

Source dirs are resolved relative to the context directory.

### Artifact repositories (prepared for future use)

```toml
[repositories]
sources = [
    "github:yakoon-runtime/apps",
    "gitlab:company/internal",
]
```

This section is parsed by the context model but not yet active.
It will describe where to find published artifacts for `install` and `sync`.

### How sources are used

```
CLI
 │
 ▼
Context.current()
 │
 ▼
context.resolve_sources()  → [./packs, ./runtime, ./apps, ...]
 │
 ▼
FileRepository(*sources)     → finds pack.toml, resolves distributions
DirectoryArtifactStore(*sources) → finds artifacts, resolves mounts
```

There is no architectural difference between "core" and "product"
components. The only difference is which sources the context provides.
