# ADR 20: Source Catalogs — Context knows sources, catalogs list resources, the index resolves

**Status: Proposed**

ADR-8 unified resolution around the Environment and made identities opaque.
This ADR simplifies the *where* one step further, toward the model of a
package manager (apt/pip): a source provides a catalog, the catalogs merge
into one local index, and the Environment resolves against that index. The
installer no longer searches anything.

> **A component's origin is a source; a source's contents are a catalog;
> the merged catalogs are the index the Environment resolves against.**

## Model

```
Context       → Which sources do I know?       (a flat list)
Catalog       → Which resources does a source offer?
Index         → The merged, local view of all catalogs
Environment   → Which components do I want?
```

A source is the only concept for *where* something comes from. A local
development checkout, a GitHub repository, and a third-party catalog are
all sources — no separate mechanisms, no family prefixes, no overrides.

## Vocabulary

> **Source** — anything that answers "what do you offer?" A list that may
> contain further sources, components, and environments.

> **Catalog** — the resource a source serves: `sources:`, `components:`,
> `environments:`. A catalog is transport-agnostic.

> **Index** — the merged local view built by walking the source graph.

> **Environment** — the desired installation: an exact list of component
> identities (unchanged from ADR-8).

## Context

ADR-8 resolved each component through an explicit source mapping
(`[sources] crm = "../crm"`) or by searching repositories. Both are still
two different mechanisms, and the repository search re-scans GitHub on every
`add`. A package manager instead builds a catalog once and resolves against
it. The coming repository split makes this decisive: when Yakoon's single
repo becomes several, only the source lists change — Yak never notices.

## Decision

### 1. The Context lists sources flatly

```toml
# .yak/context.toml
sources = [
    "/home/stefan/dev/crm",
    "github:acme/components",
    "yakoon:official",
]
```

No distinction between repositories, development sources, official and
third-party. Each entry is a source. `yakoon:official` is a bootstrap
alias; a local directory is a source like any other.

### 2. A source is a recursive list

A catalog may contain further sources, components, and environments:

```yaml
# catalog.yml
sources:
  - github:yakoon-runtime/sdk/catalog.yml

components:
  y5n-apps-shell:
    version: 0.4.0
    location: releases/y5n-apps-shell-v0.4.0/y5n-apps-shell.artifact.tar.gz
    fingerprint: sha256:...

environments:
  yakoon:platform:
    location: environments/yakoon-platform.yml
```

Yak understands exactly one rule:

> **Load a list → collect its entries → follow further lists.**

The graph is walked and flattened into the index. No fixed hierarchy
(`main → repo → component`) exists in code.

### 2a. A source repo declares its own catalog

Open question 1 is decided: **a source repository carries a declared
`catalog.yml`** — never recursive discovery. No walking directories for
`pack.toml`, `pyproject.toml`, or `.csproj` to guess what is a component.
The catalog says "I offer `y5n-runtime-engine`; here it is", it does not
derive the name from a folder:

```yaml
# runtime/catalog.yml
components:
  y5n-packs-root:
    location: packs/y5n-packs-root
  y5n-runtime-boot:
    location: runtime/y5n-runtime-boot
  y5n-runtime-api:
    location: runtime/y5n-runtime-api
```

The component's own metadata stays authoritative for its identity. On load
Yak verifies `catalog identity == component identity` and fails otherwise —
the declared name and the component's own name must agree. No name
derivation in either direction.

### 3. The yak wheel carries only the root pointer

The shipped default is a single bootstrap source — the official source-list
alias. The wheel does not know `runtime`, `apps`, `sdk`, or any component
name. Tomorrow's official repository structure can change completely without
a new `yak` release.

### 4. Resolution is an index lookup

```
yak install / add / update
    ↓
sources from context
    ↓
catalogs loaded, source graph walked
    ↓
in-memory merged index
    ↓
resolve(exact component identity) → location
```

The first exact hit wins. **Source order is depth-first, declaration
order** — a source's own resources and its entire subtree precede the next
declared source:

```
Context source 1
├── its own resources
├── child source 1 → recursively
├── child source 2 → recursively
Context source 2
└── ...
```

This keeps the intuitive rule true: **what is declared earlier as a source
has complete precedence.** For `sources = ["/home/stefan/dev",
"yakoon:official"]` the whole local development graph wins over Official.
The graph walk includes cycle detection (`A → B → C → A` is a load error) —
necessary hygiene, not new architecture.

### 5. A writable repository owns its catalog

> **A writable repository owns and maintains its catalog. A successful
> deploy means that both resource and catalog are consistent and
> immediately resolvable.**

`deploy(resource)` is one atomic repository operation: write the artifact
and update the catalog together. There is no state where the artifact exists
but the catalog ignores it, or where the catalog points at an artifact that
failed to upload. GitHub, S3, HTTP, a filesystem, or a USB stick implement
this differently; Yak knows none of it.

### 6. Locations are source-relative

A catalog holds `location` relative to its source, never an absolute
GitHub URL — otherwise the "transport-agnostic" catalog would be full of
GitHub URLs and worthless the moment a repository is mirrored or mounted
as a filesystem. The source adapter interprets the relative location.

### 7. No caching architecture yet

For 0.4 the index is built in memory on each command. A persisted index
(`~/.yak/index/`) with fingerprints, TTL, and offline mode is deferred until
loading a few YAML files measurably matters.

## Consequences

### Benefits

- **One mechanism.** Local dev, official, third-party, and overrides are all
  sources with precedence — no mappings, no repositories vs. development
  sources, no family prefixes.
- **No searching.** The installer scans nothing; it builds an index once and
  resolves exact identities. `resolve_environment` as a special repository
  method disappears — environments are catalog resources.
- **Transport-agnostic repositories.** GitHub becomes plain transport. The
  catalog is the contract; S3/HTTP/filesystem/USB follow later.
- **The repository split becomes list editing.** Splitting Yakoon's single
  repo into several changes only the source lists; Yak is unaffected.
- **The ADR-8 invariants survive unchanged.** Environment = WAS, Context =
  WO, identities are opaque, no name magic. Only the WO is now consistent.

### Trade-offs

- **Catalog freshness on the write side.** A writable repository must keep
  its catalog consistent on every deploy; the deploy contract grows.
- **Source-order precedence is global.** Two sources offering the same
  component: first wins — a local source first shadows everything else,
  which is exactly the intended development behavior but must be explicit.
- **Catalog maintenance.** Every official repository carries its catalog;
  the source graph must be kept in sync when repositories are added or
  removed.

## Open questions

1. **Deploy targets.** The flat `sources` is the read side. Writable targets
   (`--to github:...`, named targets) stay separate — but the named
   `[repositories]` section may shrink or disappear.
2. **Version semantics.** The catalog carries a version per component. For
   0.4 resolution is exact-by-name with first-match precedence; pinning and
   conflict resolution (multiple versions of one component) are future work.
3. **Catalog freshness on the read side.** Re-fetch on every command (0.4)
   vs. a cached index; fingerprints could make refreshes cheap.

## Implementation sketch

Built in two isolated steps on a fresh branch — the read side first:

1. **Read side (proves the model):** Context parses `sources` as a flat
   list; the catalog loader reads `sources:`, `components:`,
   `environments:` (declared, no discovery) and verifies catalog identity
   against component identity; the index walks the graph depth-first with
   cycle detection and merges into `{name: {source, version, location,
   fingerprint}}`; resolution is an exact index lookup. Proof: `add
   cool-shell`, `add y5n-packs-ident` and a local checkout all resolve
   through the same index; source order decides; removing a local source
   returns to the released artifact.
2. **Write side:** a writable repository updates its resource and its
   catalog atomically; `deploy(resource)` leaves the repository consistent
   and immediately resolvable.
