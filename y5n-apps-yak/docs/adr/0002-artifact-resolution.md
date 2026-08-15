# ADR 002: Artifact Resolution

**Status:** Accepted  
**Date:** 2026-07-25

---

## Context

Yakoon needs installable artifacts for Runtime, SDK, Shell, and Packs.
During development, local artifacts should be usable without publication.
Later, the same commands must work with an enterprise or public registry.

The current `install` command works around the absence of artifacts by
installing from the monorepo via editable pip installs. This is a
development‑time bridge, not a long‑term solution.

---

## Decision

### Architecture

Three independent layers:

```
yak install <artifact>
         │
         ▼
  Artifact Resolver     — resolves a name to a concrete artifact descriptor
         │
         ▼
       Source           — provides bytes (filesystem, HTTP, Git, S3, …)
         │
         ▼
  Artifact Provider     — understands the format (wheel, gem, zip, nuget, …)
         │
         ▼
     Installer          — places the artifact in the target environment
```

| Layer | Responsibility | Does not know |
|-------|---------------|---------------|
| Artifact Resolver | maps name → artifact descriptor | sources, formats |
| Source | delivers bytes | formats, installation |
| Artifact Provider | interprets bytes (format) | sources, installation targets |
| Installer | places artifact | sources, formats |

This mirrors the Runtime architecture:

```
Runtime:      Resolver → Transport → Executor
Packaging:    Resolver → Source → Provider → Installer
```

### 1. `yak build` — materialize artifacts

`yak build` produces artifacts from projects in a Yakoon repository. The
build delegates to a **build backend** selected by the project's metadata.

The first implementation produces Python wheels. Future backends may produce
other formats (tarballs, gems, dotnet DLLs).

Build output goes to a configurable artifact store (default `~/.yak/artifacts/`).

### 2. Sources — where bytes come from

Sources deliver raw bytes. They do not interpret the format.

| Source kind | Bytes come from |
|-------------|-----------------|
| `directory` | A local folder |
| `pypi` | PyPI simple API |
| `http` | A plain web server |
| `git` | A Git repository tag |
| `s3` | Cloud storage |
| `registry` | A Yakoon-specific registry |

### 3. Artifact Providers — what the bytes mean

Providers interpret the byte stream and expose a standard installation
interface. The first provider handles Python wheels.

| Provider | Interprets |
|----------|------------|
| `wheel` | `.whl` files (Python) |
| `gem` | `.gem` files (Ruby) |
| `nuget` | `.nupkg` files (.NET) |
| `zip` | `.zip` archives (any language) |

### 4. `yak install` — no special cases

All installations use the same resolver chain:

```bash
yak install dev       # Developer distribution (runtime + shell + sdk)
yak install runtime   # Runtime only
yak install crm       # CRM pack
```

The command never knows where a package came from or what format it is.

### 5. `pip install yakoon` — CLI only

Installs only:
- the `yak` CLI
- default configuration
- default resolver chain

Not: Runtime, SDK, Shell, or Web. These are regular artifacts resolved at
install time.

---

## Configuration

Sources are configured in `~/.yak/config.toml`. The Artifact Provider is
derived from the artifact metadata (e.g. a wheel's `METADATA` declares its
format).

```toml
[sources]
order = ["local", "enterprise", "public"]

[[source]]
name = "local"
kind = "directory"
path = "~/.yak/artifacts"

[[source]]
name = "enterprise"
kind = "http"
url = "https://packages.acme.local"

[[source]]
name = "public"
kind = "pypi"
url = "https://pypi.org/simple"
```

Enterprise with air‑gapped policies, using only Ruby gems from internal Git:

```toml
[sources]
order = ["internal"]

[[source]]
name = "internal"
kind = "git"
url = "https://git.internal.corp/yakoon-packs"
```

---

## Principles

### The resolver knows names, not sources or formats

```
resolve("runtime")
  → Source 1 (local)
  → Source 2 (enterprise)
  → Source 3 (PyPI)
  → first match wins
```

No logic like `if developer:` or `if python:` or `if local:`.

### Source and Provider are independent

A Source delivers bytes. A Provider interprets them. An HTTP server can
serve wheels, gems, zips, or NuGet packages — the Source doesn't care.

### Language neutrality

The word "wheel" appears nowhere in the architecture. Wheels are merely
the first concrete implementation of an Artifact Provider.

---

## Consequences

- `install dev` becomes a meta‑package resolved through the standard chain.
- `yak build` decouples development from publication.
- No special cases in the install command.
- Enterprise air‑gapped environments: configure only internal sources,
  remove public sources entirely.
- The resolver pattern extends naturally to `yak publish`, dependency
  resolution, and enterprise registries.
- New artifact formats can be added without changing the resolver or
  the install command — only a new Provider.
