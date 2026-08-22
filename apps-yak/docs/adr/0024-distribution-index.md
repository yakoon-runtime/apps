# ADR 24: Distribution Index — Install Resolves Against a Distribution, Not Source Repositories

**Status:** Accepted
**Date:** 2026-08-22
**Verified:** 2026-08-22 — the central slice is proven end to end (see
"Vertical proof" below).

## Context

Installation today is a **federated source resolver**: `yak install runtime`
reads the Context sources, fetches every source's remote `catalog.yml`
through the GitHub Contents API, builds a merged in-memory index, resolves
the bundle, then reads a component-local `.yak/releases.yml` per member and
downloads the artifact.

Two things make this uncomfortable.

**First, the request profile.** One `install` costs roughly 17 unauthenticated
GitHub API calls (8 catalogs + up to 9 release files + downloads). The
unauthenticated budget is 60 requests/hour **per IP** and is shared by NAT'd
machines; a handful of commands exhaust it and installs start failing with
`HTTP 403: rate limit exceeded`. The Contents API becomes an accidental hard
dependency of installation.

**Second, the model.** ADR-20 already deferred a cached/persisted index
("No caching architecture yet", open question 3: *re-fetch on every command
vs. a cached index*). The 60-second per-file cache layered on later is an
interim, not the design. But the deeper issue is not the cache: it is that
Yakoon made the **source-catalog graph** its **remote distribution protocol**.

Established package managers do not work this way:

| | PyPI | npm | apt | Cargo | OCI |
|---|---|---|---|---|---|
| Consumer reads | `simple/{name}` index | registry JSON per package | `Packages` file per suite | sparse per-crate index | tag → manifest |
| Integrity | hash in index | `integrity` sha512 | sha256 in index | checksum in index | digest-addressed |
| Crawls source repos? | **no** | **no** | **no** | **no** | **no** |

The shared invariant: a **distribution is its own, consumer-served object**
— materialized at publish time, carrying `name + version + digest + url
(+ dependencies)`, fetched once, everything after it is local and
digest-verified. Source repositories are irrelevant to consumers.

Yakoon already has the producer side of this (ADR-23): `.yak/component.yml`
(identity), artifacts with `artifact.yml`, published GitHub releases. What
is missing is the **distribution layer**.

## Decision

### 1. Five layers, each with one owner

```text
SOURCE
  .yak/component.yml
        │
        │ yak build
        ▼
ARTIFACT
  artifact.yml + payload
        │
        │ yak publish
        ▼
PUBLISHED ARTIFACT
  GitHub Release / later any host
        │
        │ yak deploy
        ▼
DISTRIBUTION
  distribution.yml
        │
        │ yak install
        ▼
INSTALLATION
  state.yml + deployment.yml
```

| Layer | File | Answers |
|---|---|---|
| Component | `.yak/component.yml` | What is built? (`name`, `version`) |
| Artifact | `artifact.yml + payload` | What was built? |
| Published artifact | host + release asset | Where is it physically? |
| Distribution | `distribution.yml` | What can Yak install? |
| Installation | `.yak/state.yml` + `.yak/deployment.yml` | What runs, and how? |

### 2. Precise command semantics

- `yak build` — produces an immutable artifact from a component.
- `yak publish` — makes that artifact available physically (a GitHub
  release asset today; any host later).
- `yak deploy` — accepts a *published* artifact into a distribution.
- `yak install` — resolves against a distribution, downloads the artifact,
  verifies the digest, installs.

`deploy` therefore means "make this published build installable", not "write
a file into a source repository".

### 3. The install contract

`yak install` knows **neither Git repositories, nor `component.yml`, nor the
GitHub Contents API**. It knows only:

- a distribution address (one metadata fetch),
- artifact URLs and their digests,
- the digest as the trust anchor — an artifact must match its recorded
  digest before it is used.

### 4. The distribution index is a materialized projection

`distribution.yml` is the consumer-optimized view of what an organization
offers — **distribution-owned**, not a second component-authority:

```yaml
components:
  y5n-runtime-engine:
    releases:
      0.7.0:
        url: https://…/y5n-runtime-engine-v0.7.0/y5n-runtime-engine.artifact.tar.gz
        digest: sha256:…
      0.8.0:
        url: https://…/y5n-runtime-engine-v0.8.0/y5n-runtime-engine.artifact.tar.gz
        digest: sha256:…
bundles:
  runtime:
    components:
      - y5n-runtime-api
      - y5n-runtime-engine
      - y5n-runtime-store
```

It is served as a **static object over plain HTTP/HTTPS** (a repo raw URL or
any CDN), not through a Contents-API-bound protocol. The release history of
every component lives here, so distribution can evolve — channels
(`stable → 0.8.0`, `beta → 0.9.0`), yanking, mirrors — **without rewriting
source repositories**.

### 5. ADR-0020 is partially retained

Catalogs and the merged index remain exactly right for the **source /
development** path: `--path` catalogs, local checkouts, resolving editable
sources. The superseded assumption is only that *the catalog graph must
simultaneously be the remote distribution protocol for consumers*. ADR-0020
is not dissolved; its remote-distribution role is replaced by the
distribution index.

### 6. Integrity is carried by the distribution

`(name, version)` selects a build; `digest` *is* the build identity for
consumption. URL is publisher-specific and may change (mirror/migration)
without changing the digest. Consumers never trust a URL, only the digest
recorded in the distribution.

### 7. The component release file is retired

`<component>/.yak/releases.yml` is **removed from the model**. Its purpose
— giving the consumer `tag + digest` of the currently offered build — is
now the distribution's job. Two release lists would be dangerous (they
would drift), so there is exactly one:

```text
component.yml       → Source-Authority      (name, version)
artifact.yml        → Build-Authority       (kind, deps, fingerprint)
distribution.yml    → Release-/Distribution-Authority (releases by version, digest, url)
state.yml           → Installation-Authority
deployment.yml      → Operations-Authority
```

`yak deploy` therefore **never writes back into a component/source
repository**. It writes the projection only.

### 8. Distribution ownership and addressing

A distribution has its **own owner** — not `runtime`, not `apps`, not any
component. Initially a dedicated repository:

```text
yakoon-runtime/dists
└── distribution.yml
```

This is a direct continuation of ADR-0023's
`distribution = "github:yakoon-runtime/dists"`. The abstraction boundary
matters more than the concrete host:

```text
distribution
    producer: github:yakoon-runtime/dists   (yak deploy)
    consumer: https://…/distribution.yml     (yak install)
```

`github:` is the **producer address**; the **consumer address is a plain
HTTP(S) URL** (a static object — whether via `raw.githubusercontent.com`
or a CDN is decided in the vertical slice). A distribution is a URL, not
GitHub.

### 9. Dependencies: authority is the artifact, materialized into the distribution

Dependencies **belong in the distribution index — but are never authored
there** (like a database index: redundant in storage, never redundant in
authorship).

```text
artifact.yml
dependencies: …
        │
        │ yak deploy
        ▼
distribution.yml
components:
  foo:
    releases:
      1.2.0:
        dependencies: …
```

They must be there because otherwise the resolver would have to download
every artifact before knowing its dependency graph — which would make the
consumer-optimized index incomplete. So:

> **The artifact is the authority for dependencies. The distribution
> materializes them for resolution.**

`yak install runtime` can then compute the complete dependency graph from
**one** metadata fetch, before any artifact is downloaded.

## Consequences

### Benefits

- **One metadata request per install** instead of ~17 Contents-API calls;
  the 60-requests/hour ceiling leaves the consumer model.
- **No Contents-API lock-in** for installation — plain HTTP, CDN-cacheable,
  mirror-able, offline-capable (a cached distribution.yml).
- **Source repos stop being the consumer protocol** — consistent with
  pip/npm/apt/cargo/OCI.
- **Clean vocabulary**: build / publish / deploy / install each mean one
  thing; the three worlds (component, distribution, installation) are
  separated, so repository state, software distribution and deployment
  configuration stop sharing one model.
- **`deploy` becomes a real deployment** — your published build becomes
  installable, and later `stable`/`beta`/yank are distribution concerns.

### Trade-offs

- The distribution index must be **maintained on the write side**: `deploy`
  both ensures the artifact is published and updates the projection. This is
  exactly the package-manager "publish writes the index" contract.
- **Trust/signing** moves into the distribution layer (the digest is the
  anchor; signing the index itself is a future concern).
- Two resolution paths now exist (source/dev catalogs vs. distribution) —
  their precedence and overlap must be explicit.
- The component release file is retired: component release history lives in
  the distribution, and one release list exists instead of two.

## Decisions on the open questions

1. **`<component>/.yak/releases.yml` — RETIRED.** The distribution carries
   the full release history; `tag + digest` for consumption comes from
   there. `deploy` never writes back into a source repo.
2. **Distribution ownership — a dedicated distribution owner**, initially
   the `yakoon-runtime/dists` repository. The **consumer protocol is
   HTTP(S), not the GitHub API**: a distribution is a URL, not GitHub.
   `github:` remains only the producer address for `deploy`.
3. **Dependencies — authority is the artifact** (`artifact.yml`),
   **materialized into the distribution at `deploy`**. The distribution
   thereby contains complete resolver metadata (one fetch → full dependency
   graph), without ever being hand-authored.

*Status: Accepted.* The three decisions are implemented by the vertical
slice; the legacy remote-Catalog/`releases.yml` path is removed (see the
follow-up).

## Vertical proof

The exact scenario that triggered this ADR, as an acceptance test: with a
**fully exhausted GitHub Contents API budget** (`core remaining: 0/60`),
the consumer path still installs, because it never touches the Contents
API:

```text
yak init
yak install system          ✓ resolve via one GET distribution.yml
                            ✓ dependency closure from the distribution
                            ✓ artifacts digest-verified over HTTP
                            ✓ installed (state.yml written)
yak install runtime         ✓ the same, for the full runtime bundle
```

- Distribution is served as a static HTTP object
  (`raw.githubusercontent.com/yakoon-runtime/dists/main/distribution.yml`);
  artifact downloads go over the release-asset CDN — no `api.github.com`.
- `install system` installed `y5n-caps-system` plus its transitive
  distribution-known dependencies (`y5n-runtime-api`, `y5n-sdk-python`).
- `install runtime` installed all nine runtime components in one pip
  transaction, each digest-verified.

This proves the ADR's central claim: **distribution is independent of
source discovery.**

## Removing the legacy path

After acceptance, the intermediate consumer route is deleted:

```text
remote catalog
    ↓
component location
    ↓
.yak/releases.yml
    ↓
GitHub Contents API
    ↓
artifact
```

Resolution becomes strictly:

```text
yak install <x>

Distribution present?
    ├── yes → DistributionResolver only
    │         (no Contents API, no remote catalog crawl, no releases.yml)
    └── --path / source mode → CatalogResolver, local sources
```

No silent fallback from a distribution to remote catalogs. Catalogs and the
index remain the source/development model (ADR-0020); only the
remote-distribution hybrid is gone.

## Follow-up — a context owns ordered distributions

A context can list **several distributions** in order; the resolver merges
them into one installable universe, and for an identical identity (component
or bundle) **the later distribution wins**:

```toml
# .yak/context.toml
distributions = [
  "https://…/yakoon-runtime/dists/distribution.yml",
  "https://…/acme/dists/distribution.yml",
]
```

```text
yak install runtime       → the `runtime` bundle from whichever offers it (later wins)
yak install acme-crm      → ACME's own cap
```

There is **no special default origin**: Yakoon itself uses the same
mechanism as anyone else, identity stays separate from origin, and no
`extends` or company copy of the official index exists. Two static HTTP
requests (official + company), merged locally.

## Implementation sketch

One vertical slice, then generalization:

1. **Read side:** `install` resolves a component/bundle against a
   distribution URL (`GET distribution.yml`, cached); downloads the selected
   artifact; verifies the digest; installs. No catalogs, no Contents API on
   this path.
2. **Write side:** `deploy` takes a published artifact and enters
   `{name, version → url, digest}` (+ bundle membership) into the
   distribution — the projection is updated atomically.
3. **Source/dev path:** `--path`/catalog resolution stays unchanged; the two
   paths meet in the same `Installation` layer (state.yml / deployment.yml).
4. Prove the consumer slice against the existing published artifacts first
   (single distribution document, empty-budget install), then run the full
   lifecycle: build → publish → deploy → install in a fresh directory.