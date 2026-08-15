# ADR 21: The Install Contract — Component, Bundle, and Where-From

**Status:** Accepted
**Date:** 2026-08-15

## Context

Composing a Yak environment needs three commands today: `install`
(baseline from artifacts), `bootstrap` (baseline from local sources) and
`add` (further components). After ADR-20 separated source and artifact
per component (`location` vs `release`), these verbs describe variants of
one operation: *make this component part of this environment.* The mode
is a property of each resolved component, not of the invocation.

## Decision

There is one composition primitive:

```text
yak install <component|bundle> [--path <catalog>]...
```

- The first argument is always an **identity**: a component name or a
  bundle name.
- `--path` is an optional **source override**: it points to a *source
  with a `catalog.yml`* (never directly at a component). Paths are
  repeatable and considered preferentially.
- `bootstrap.toml` carries only the known remote sources; the
  `install = [...]` baseline list is removed.
- `add` and `bootstrap` are removed.

### Resolution — per component

```text
                    install target
                          │
                 Component / Bundle
                          │
                 component names
                          │
                 for each component
                          │
              ┌───────────┴───────────┐
              │                       │
     in any --path catalog?          no
              │                       │
          location                 release
              │                       │
           SOURCE                  ARTIFACT
              └───────────┬───────────┘
                          │
                    same lifecycle
```

A component resolved from a `--path` catalog uses its `location`
(source). Everything else resolves through the remote index using its
`release` (artifact). There is no global mode: an installation can hold
`runtime-api = source` and `sdk-python = artifact` at the same time.

### Bundles — composition without recursion

A bundle is a name → list of component names:

```yaml
bundles:
  runtime:
    - y5n-packs-root
    - y5n-runtime-boot
    - y5n-runtime-api
    - y5n-runtime-engine
    - y5n-runtime-store
    - y5n-runtime-transport
    - y5n-runtime-llm
    - y5n-sdk-python
    - y5n-apps-runtime
```

- Bundles are **global**: the names resolve through the shared index
  (first hit wins), independent of the repository that declares the
  bundle. Moving a component to another repo does not change the bundle.
- Bundles contain **components only** — never other bundles (no
  recursion, no cycles, no ordering concerns) in this version.

### Source and artifact stay per component

The catalog keeps both faces of a component:

```yaml
components:
  y5n-runtime-api:
    location: packages/y5n-runtime-api   # source
    release: y5n-runtime-api-v0.8.0      # artifact
```

`location` answers *where the source is*; `release` answers *which
published release to use*. The transport knows how to turn `release`
into an artifact address; the catalog never reasons about tags or
versions.

## Consequences

- One primitive for composition; identity is always explicit.
- `--path` is a source override, not a "source mode": components absent
  from a local catalog still resolve as releases.
- Granularity: `install runtime` (all releases) up to
  `install runtime --path ./runtime --path ./sdk --path ./apps`
  (everything source).
- `add`, `bootstrap` and the `install = [...]` baseline list disappear.
