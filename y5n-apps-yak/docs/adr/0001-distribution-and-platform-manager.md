# ADR 001: Distribution and Platform Manager

**Status:** Implemented  
**Date:** 2026-07-25

## Context

Yakoon has evolved from a monorepo into a modular ecosystem of Runtime, SDK, and
Packs (apps).  During this evolution, `scripts/` accumulated concerns from all
layers: workspace building, database setup, remote testing, and global
installation.  A closer look revealed four distinct categories:

| Script | Responsibility | Should belong to |
|---|---|---|
| `install.sh` | Workspace setup / development env | **Distribution** |
| `build-workspace.py` | Workspace builder | `workspace/tools/` or `runtime/y5n-runtime-boot` |
| `setup-db.sh` / `setup-db/crm.sh` | CRM database installation | `y5n-packs-crm` |
| `test-remote.py` | Runtime demo / lab | `y5n-packs-labs` or `runtime/examples` |

Each script belongs with the component whose lifecycle it supports.  The only
script that legitimately spans the whole repository is `install.sh` — but even
that raised a deeper question: *what is it installing?*

The answer revealed a missing layer: **Distribution**.

## Decision

### Location: `yak/` is independent of `runtime/`

`yak` lives at the repository root, not inside `runtime/`.  The two are
independent products with their own lifecycles:

```
yakoon/
    docs/
    runtime/          — execution environment
    repos/            — optional packs
    yak/              — platform manager (resolver, materializer, CLI)
```

They are independent in the sense of the deletion test:

- Delete `yak` → runtime still runs with an existing instance.
- Delete `runtime` → `yak` can still resolve distributions, compute
  dependencies, and materialize a workspace — it just can't execute it.

Each has its own `pyproject.toml` and versioning.  Python is the initial
implementation language for `yak`; the interface could be ported later
(e.g. `cargo install yak`, `brew install yak`).

We introduce four distinct layers that replace the implicit concept of
"workspace" and the monolithic `install.sh`:

```
Distribution         — declarative description of a platform
      ↓
Resolver             — resolves pack names, builds a dependency DAG
      ↓
Materializer         — translates the resolved pack set into a concrete instance
      ↓
Runtime              — executes the instance; knows nothing above it
```

### Layer boundaries

| Layer | Knows | Responsibility |
|---|---|---|
| **Distribution** | Pack names (and optionally version constraints) | "What packs make up this platform?" |
| **Resolver** | Repository providers, dependency resolution | "Which concrete packs are needed?" |
| **Materializer** | Pack layout, structure mounting, setup scripts | "How does the instance look on disk?" |
| **Runtime** | The materialized instance only | "Run it." |

### Scope: Platform Orchestrator, not just Installer

`yak` is more than an installer — it is the **Platform Orchestrator**.
Its responsibilities span the full lifecycle:

| Command | Responsibility |
|---|---|
| `yak resolve` | Show the resolved pack graph |
| `yak materialize` | Build the workspace on disk |
| `yak install` | Resolve + materialize + run setup hooks |
| `yak update` | Update packs to new versions |
| `yak run` | Start runtime (and optional companion services) |
| `yak stop` | Gracefully shut down |
| `yak status` | Health of all components |
| `yak doctor` | Diagnose configuration and connectivity |
| `yak deploy` | Push to a target environment |

Think of it as `docker compose` for Yakoon — but instead of containers, it
manages Runtime, Viewer, WebServer, and any other component that forms the
platform.  The Runtime itself knows nothing about this; it only receives a
materialized workspace.

### The Platform Manager: `yak`

`yak` is an **engine with multiple hosts**, mirroring the runtime's own
architecture (API → Host → Transport).  Its core is a library:

```
yak/
    resolver/         — dependency graph resolution
    materializer/     — workspace/materialization
    repository/       — pack source providers (local, git, registry)
    distribution/     — distribution format and parsing
    cli/              — one host among many
```

The CLI is just one entry point:

```bash
pip install yak            # one-time install
yak install crm             # resolve + materialize + start
```

The same API can be consumed by Docker, CI/CD, or a GUI:

```dockerfile
FROM python:3.13
RUN pip install yak
COPY crm.toml .
RUN python -c "from yak import install; install('crm')"
CMD ["runtime"]
```

`yak` contains no Runtime code.  It orchestrates the upper three layers
(Resolver, Materializer, Repository) and produces a materialized instance
that the Runtime can execute.

### Two runtimes

`yak` is itself a runtime — a **Platform Runtime** — operating one level above
the **Application Runtime** (`runtime/`):

```
Platform Runtime (yak)
    distribution.toml → Resolver → Materializer → Workspace
        │
        ▼
Application Runtime (runtime/)
    Workspace → Engine → Session → Command
```

Both are runtimes in the Yakoon sense: they take a declarative description and
produce behavior.  They operate on different models:

| | Platform Runtime | Application Runtime |
|---|---|---|
| Input | `distribution.toml` | Workspace |
| Output | Workspace | Session / Command |
| Primitives | Packs, Distributions | Ports, Invocations |
| Execution | Resolver → Materializer | Engine → Transport |

They are independent products (separate `pyproject.toml`, separate versioning)
but share the same architectural DNA: "Describe → Resolve → Materialize →
Execute".

### Docker is not a special case

Docker uses the same `yak` library as the CLI — the materialization logic
is not duplicated.  Whether invoked from the command line, a Dockerfile, a
GitHub Action, or a GUI, the result is identical: a self-contained instance
that the Runtime can execute.  The CLI is merely one host over the
`yak` engine, just as the terminal transport is one host over the Runtime
engine.

### Distribution as a product

A distribution is a declarative file (`distribution.toml`):

```toml
name = "crm"
version = "1.0"

[[packs]]
name = "runtime"

[[packs]]
name = "system"

[[packs]]
name = "ident"

[[packs]]
name = "crm"
```

Distributions can reference other distributions, forming a composition tree:

```toml
name = "acme-erp"

[[distribution]]
name = "crm"

[[packs]]
name = "acme.erp"
```

The Resolver flattens the tree into a unique set of packs.

### Repository provider abstraction

The Resolver queries `Repository` providers through an interface:

```python
pack = repository.resolve("crm")
```

Initially only a `LocalRepository` over `repos/*` exists.  The interface
allows `GitRepository`, `CompanyRepository`, or a public registry later,
without changing the Resolver.

### Materialization replaces workspace assembly

The Materializer:

1. Receives the resolved pack list
2. Clones or symlinks each pack
3. Mounts `structure/` entries
4. Runs per-pack setup scripts
5. Produces the instance on disk

The result is a **self-contained instance** — not a development workspace.

### The recurring pattern

This continues the architectural pattern already visible across Yakoon:

| Concern | Describe | Resolve | Materialize | Execute |
|---|---|---|---|---|
| Invocation | Port / Method | Routing | Transport | Engine |
| Dialog | Form / Fields | Validation | UI rendering | Submit |
| **Platform** | **distribution.toml** | **Resolver** | **Materializer** | **Runtime** |

"Describe → Resolve → Materialize → Execute" emerges as a core Yakoon principle.

## Consequences

### Positive

- `scripts/` dissolves cleanly: each tool moves to its component.
- `install.sh` is replaced by `yak install`, which is language-agnostic.
- Runtime remains completely unaware of distribution concerns.
- Distributions become shareable, combinable, versionable products.
- Partners can define custom distributions without touching core Yakoon.

### Negative

- Requires building and maintaining the `yak` tool (initially Python, could be
  ported later — Python is an implementation detail).
- The Materializer needs to handle pack acquisition (local repos, git, etc.).
- Existing `scripts/` users need migration.
- Distribution format and Resolver logic must be designed carefully to avoid
  feature creep.

### Neutral

- The term "workspace" shifts from a development concept to a materialization
  output.  We may want to rename it to "instance" over time.
- `yak` becomes the single entry point; documentation must reflect that.
