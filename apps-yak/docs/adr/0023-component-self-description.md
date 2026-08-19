# ADR 23: Component Self-Description — Where a Yakoon Component Tells Its Own Story

**Status:** Accepted
**Date:** 2026-08-17
**Updated:** 2026-08-19 — Step 4 (catalog mapping + repository-local
`releases.yml`). Section 4 and Section 5 and the Step 3 notes that
describe a remote per-location `component.yml` fetch are **superseded
for the catalog shape and the remote resolution path**; everything about
`.yak/` being the portable component contract and `component.yml` owning
identity/version is unchanged.

## Context

A Yakoon component is language-neutral by ambition, but its metadata is
not. Today a component describes itself through a patchwork of files,
most of which are language-specific:

- `pyproject.toml` is the single source of identity and version — for
  Python.
- `.yak/mount.yml` declares the mount target.
- `catalog.yml` repeats the identity as a key, declares `location`
  (discovery) and `bundles`.
- `artifact.yml` (in a built artifact) repeats name, version, kind,
  builder, host, mount.
- `catalog.yml → release:` declares release info — and is **dead
  configuration**: `ComponentRef` only parses `location`, never
  `release` (resolver/catalog.py).
- `context.toml` / `sources.toml` carry a **single global**
  `distribution = "github:yakoon-runtime/dists"`.

These Yakoon metadata files are scattered flat across the repository
root, mixed with language-specific build metadata (`pyproject.toml`),
source, and documentation. There is no visible boundary that says
*this belongs to the Yakoon component infrastructure.*

The concrete outcome: identity and version exist in up to five places
(pyproject ↔ catalog key ↔ released tag ↔ artifact.yml ↔ the dead
`release:` entry), every component — including a company's private one —
must release through one global repository, and the builder is the only
component that may know a version at all. All three have since been
resolved: identity/version live authoritatively in `.yak/component.yml`
(Steps 1–2 below), and distribution follows the catalog's source, so no
global repository remains (Step 3).

## Audit finding

### Metadata files at the component boundary

| File | Level | Content | Language-dependent |
|------|-------|---------|--------------------|
| `pyproject.toml` | component | name, version, deps, build-system | **yes (Python)** |
| `.yak/mount.yml` | component | `path = "/usr/bin"` | no |
| `catalog.yml` | repo / bundle | `components: <location list>`, `bundles:` | no |
| `structure/.yak/yak.yml` | component structure | tree behavior: title, stores, resolvable, host, entry | no |
| `artifact.yml` | built artifact | name, version, kind, builder, host, mount, fingerprint | partially |
| `sources.toml` / `context.toml` | context | `sources` | no |
| `pack.toml` | — | does not exist anymore (ADR-8 → native identity) | — |

### Field classification

- **Identity** — `.yak/component.yml name` (authoritative since Step 2,
  read in manager `_read_component`) · `artifact.yml name` (copy). The
  catalog-name duplicate was removed in Step 3 — the catalog declares no
  identity.
- **Version** — `.yak/component.yml version` (authoritative since Step 2;
  the build validates the wheel against it) · `artifact.yml version` ·
  release tag `{name}-v{version}` (derived). The dead `catalog.yml
  release:` field was removed in Step 3.
- **Discovery** — `catalog.yml → components: [location, …]` (only source
  of locations, ADR-20; no directory scanning).
- **Build** — `pyproject.toml [build-system]` (Python-specific) ·
  builder discovery finds pyproject.toml only (`_find_buildable_projects`).
- **Distribution** — no field anywhere (Step 3): a component's
  distribution defaults to the source of the catalog that discovered it.
- **Structure/Mount** — `.yak/mount.yml → path` · `structure/.yak/yak.yml`
  (tree behavior, lives inside the mounted structure, not at the repo
  root).
- **Bundle** — `catalog.yml → bundles`.

### The two real duplications (resolved)

1. **Identity-key** — the catalog had to know the name to use it as a
   key, and the component repeated it in pyproject.toml. Both are gone:
   the catalog lists locations, the identity lives in component.yml.
2. **Version** — one number lived in up to five places; the catalog's
   `release:` entry was an unmaintained fifth copy. Removed in Step 3.

## Decision

There is a missing boundary: **component-level metadata, owned by the
component, independent of its implementation language.**

### 1. `.yak/` — the portable Yakoon contract of a component

> **`.yak/` is the portable Yakoon contract of a component.**

The component-local `.yak/` directory is the minimum that turns any
project into a Yakoon component — not source, not build system, not
README, not catalog. It separates **required Yakoon component
infrastructure** from language-specific build metadata, source code,
documentation, and other project files.

```text
caps-system/
├── .yak/
│   ├── component.yml      REQUIRED
│   └── mount.yml          REQUIRED for structure/mount
│
├── catalog.yml             repository / discovery (above the component)
├── pyproject.toml          language-specific build metadata
├── src/                    implementation
├── structure/              delivered Yakoon structure
└── README.md               optional

README.md, tests/, scripts/  optional
pyproject.toml, *.csproj     only for the language
```

> **`.yak/` contains Yakoon-native metadata for a component.**

Not everything that touches Yakoon moves here: `catalog.yml` stays out
because it describes the repository / discovery and lives *above* the
component in multi-component repos; `structure/.yak/yak.yml` stays where
it is because it describes a **node of the materialized filesystem**, not
the component.

### 2. `.yak/component.yml` — who am I?

```yaml
# caps-system/.yak/component.yml
name: y5n-caps-system
version: 0.8.0
```

- `name` and `version` are the **Yakoon identity** of the component.
- They are language-neutral — the component's language knows how it is
  *built*; Yakoon knows what the component *is*.
- `.yak/component.yml` is the **authoritative source** for identity and
  version — not the native build metadata. The native build must prove
  the declaration, and Yakoon never relabels the result:

  > `.yak/component.yml` declares component identity and version.
  > Native build metadata must match that declaration.

  A builder may build as its technology does; if the produced artifact
  does not match the declaration, the build fails. A platform may not
  rebuild an artifact with a different name or version to force a match.
- **Scope:** this ADR decides identity and version only. Distribution is
  a per-component property of the catalog (section 5), not a component
  intrinsic.

#### Identity vs. fingerprint

`name + version` identify the **logical component release**; an artifact
fingerprint identifies a **concrete build** of that component version:

```yaml
# artifact.yml (built)
name: y5n-caps-system
version: 0.8.0
fingerprint: sha256:abc123…   # this specific build
```

Two builds of the same component version are the same logical release
with different fingerprints — the fingerprint is already the build
identity (python.py sets it from the wheel bytes; `ArtifactInfo` carries
it; `state.toml` records it).

**Rebuilding and redeploying the same component version is valid.** A
repeated build of `0.8.0` produces a new artifact with a new fingerprint;
the next version `0.9.0` is a *version step*, fundamentally different
from a rebuild. No rule is introduced that a version may only be built
once, must rise monotonically, or that a release must be new.

Distribution providers may define policies for replacing or retaining
already published artifacts — that is a distribution policy, not a
version-semantics rule, and out of this ADR's scope (section 5).

### 3. `.yak/mount.yml` — what do I deliver?

```text
<component>/
└── .yak/
    ├── component.yml       who am I? (name, version)
    └── mount.yml          what do I deliver? (structure → target)
```

`.yak/mount.yml` is Yakoon-native infrastructure (structure deployment), so
it belongs to the `.yak/` contract, not flat at the root. Its content
and semantics do not change — only its location.

A new component therefore starts with a copy of the contract and two
edits, before any implementation language is chosen:

```text
# .yak/component.yml
name: acme-caps-foo
version: 0.1.0
```

```yaml
# .yak/mount.yml
path: /opt/foo
```

Python, .NET, Go or no code at all — the Yakoon side is defined; the
technology stack (pyproject.toml, *.csproj, go.mod, structure-only)
comes afterwards, independently.

### 4. Discovery becomes pure layout

> **Superseded by Step 4 for the catalog shape.** The catalog is a
> `name → location` mapping again (Step 4 §1). This section's conclusion
> — "the catalog never declares identity" — still holds; the *shape* it
> suggests (a bare location list) does not. Validation moves from
> index-build time to the actual materialization (Step 4 §2).

`catalog.yml` only answers *where* components live; it no longer repeats
identity or carries versions:

```yaml
components:
  - location: caps/caps-root
  - location: packages/runtime-api
```

Yak navigates to a location, finds `.yak/component.yml` there, and the
component tells its own name and version. A multi-component repo works
the same as a single-component repo (`location: .`).

Layering:

```text
catalog.yml            → Where are components?
.yak/component.yml     → What is this component?
pyproject / csproj / … → How is it built for its technology?
```

In a multi-component repo the boundary becomes visible per component:

```text
runtime/
├── catalog.yml
├── packages/
│   ├── runtime-api/
│   │   ├── .yak/
│   │   │   ├── component.yml
│   │   │   └── mount.yml
│   │   ├── pyproject.toml
│   │   └── src/
│   └── runtime-engine/
│       ├── .yak/
│       │   ├── component.yml
│       │   └── mount.yml
│       ├── pyproject.toml
│       └── src/
└── caps/
    └── caps-root/
        ├── .yak/
        │   ├── component.yml
        │   └── mount.yml
        ├── pyproject.toml
        └── structure/
```

### 5. Catalog discovers by location — distribution follows the source

> **Superseded by Step 4 for the catalog shape and release resolution.**
> The catalog is a `name → location` mapping (Step 4 §1) and releases
> resolve over the repository-local `releases.yml` (Step 4 §3–4); the
> per-location `component.yml` fetch described below no longer exists.
> "Distribution follows the source" is unchanged.

A catalog lists locations only. It never declares identity (the component
owns it in `component.yml`), and it never declares distribution. The
invariant that makes this sound:

> **The catalog discovers components by location; it does not declare
> component identity.**

```yaml
# caps-system/catalog.yml — a single-component repo
components:
  - location: .

# runtime/catalog.yml — a multi-component repo
components:
  - location: packages/runtime-api
  - location: packages/runtime-boot
  - location: packages/runtime-engine
  - location: packages/runtime-store
  - location: caps/caps-root
```

Each listed location is a component root with `.yak/component.yml`. The
index resolves every location's identity from that manifest — locally
from disk, remotely through one small GitHub Contents-API request per
location (never a repo tarball). Because the catalog never names a
component, no catalog/component identity conflict can exist —
`CatalogIdentityError` is gone.

**Distribution follows the source.** A component's distribution defaults
to the source of the catalog that discovered it: a `github:owner/repo`
source publishes and resolves releases in `github:owner/repo`; a local
source carries released artifacts in its `artifacts/` directory. The
global `distribution` in `context.toml` / `sources.toml` and the `dists`
repository are removed. A bundle like `runtime` may still cross repos:
each member resolves and deploys to its *own* catalog's origin.

An explicit per-component override (`distribution: …`) is deliberately
*not* introduced today. For a split source/artifact setup the field can
later be added to a location entry and is backwards compatible:

```yaml
components:
  - location: .
    distribution: github:acme/acme-yakoon-releases
```

Semantics: no `distribution` → the catalog's source; `distribution`
present → explicit override.

The full model:

```text
COMPONENT
<component>/.yak/
├── component.yml           name, version
└── mount.yml              structure deployment

REPOSITORY / DISCOVERY
catalog.yml                 locations, bundles

SOURCE
<source>                    default distribution of its components

TECHNOLOGY
pyproject / csproj / …      build

STRUCTURE
structure/.yak/             filesystem node semantics

ENVIRONMENT
.yak/state.toml             resolved / installed versions
```

### 6. Version pinning stays out of the catalog

The catalog answers "what exists and where"; the environment/state
answers "which version I use". This ADR does not decide the pinning
syntax (`yak install system@0.8.0` or similar) — only that the catalog
never carries version pins.

## Consequences

### Benefits

- **A visible component boundary.** A developer opening a component sees
  `.yak/` at the root and immediately knows what is Yakoon-native
  infrastructure versus source, docs, or language metadata. Exactly this
  distinction guided the decision: the boundary is worth more than a
  saved directory level.
- **A portable contract.** A new component starts by copying `.yak/` and
  editing `name`, `version` and `mount` — nothing else is required to be
  a Yakoon component. The technology stack (pyproject.toml, *.csproj,
  go.mod, or structure-only) comes afterwards, independently.
- **Language neutrality.** A dotnet, Go or Ruby component describes
  itself the same way — its builder maps `.yak/component.yml` to its own
  build metadata.
- **Self-describing components.** `.yak/` contains Yakoon-native metadata
  for a component — concrete and precise, symmetric to the environment's
  `.yak/`.
- **One version source.** The fifth, dead `release:` copy disappears;
  identity and version flow from component.yml into the build — and are
  validated, not relabeled.
- **Decentral distribution.** A private company component behaves exactly
  like an official one: source, version, catalog, own releases.
- **Cleaner catalog.** Discovery is pure layout; the catalog registers
  no identities. Identity lives in one place — component.yml — and is
  validated against the native build metadata (pyproject / csproj /
  package.json) by the builder.

### Trade-offs

- **Builder coupling.** The build backend must accept or validate the
  Yakoon identity — a change to the build contract (done in Step 2).
- **Migration.** Done in Steps 1–3: every component root carries
  `.yak/component.yml` and `.yak/mount.yml`; catalogs are location lists
  (`release:` fields removed); the global distribution and `dists` are
  out of the active architecture; tags move from `dists` to each
  component repository.
- **Discovery cost.** The remote index reads the **catalogs only** — one
  Contents-API request per repository (cached briefly), never one per
  location. Releases resolve through the repository-local `releases.yml`
  over the same Contents-API transport (Step 4). This is what keeps
  remote discovery and release resolution scaling with repositories, not
  with the number of available components.
- **Identity verification.** The catalog key is a discovery binding only;
  identity is validated against the component's own contract at the
  actual materialization (source: `.yak/component.yml`, artifact:
  `artifact.yml`) and fails loudly on mismatch (Step 4 §2).

## Implementation Notes

### Step 1 (done) — the component boundary

`.yak/` was established as the portable Yakoon contract of a component:
every component root gained `.yak/component.yml` (name, version), and
`mount.toml` moved to `.yak/mount.yml` (YAML). Catalogs, builder,
version source (`pyproject.toml` stayed authoritative) and distribution
were untouched.

### Step 2 (done) — identity and version ownership

`.yak/component.yml` became the authoritative source for identity and
version. The Python builder receives the expected identity and validates
the built wheel's `Name`/`Version` against it (`_validate` in
builder/python.py); a mismatch fails the build (`IdentityMismatchError`)
— artifacts are never relabeled. The derivation chain downstream is
untouched: verified `ArtifactInfo` → `artifact.yml` → artifact filename
→ release tag → resolved artifact. The installer reads identity from
`.yak/component.yml` (`_read_component`, formerly `_read_pack`); Step 3
removed the catalog-key cross-check, since the catalog no longer
declares a name.

### Step 3 (done) — catalog discovers by location, distribution follows source

Catalogs were turned into location lists (`components: [{location: …}]`)
in every source repository. The index resolves each location's identity
from its `.yak/component.yml` — locally from disk, remotely through one
Contents-API request per location (`_fetch_component_yml`), never a repo
tarball. The management side no longer validates a catalog-declared name
(`CatalogIdentityError` is gone), because the catalog declares none.

The global `distribution` (context.toml / sources.toml) and the `dists`
repository were removed from the architecture. Resolution and deploy use
the catalog's own origin as the default distribution: `_materialize_release`
reads the component's own repo releases (or `artifacts/` for a local
source), and `deploy` routes each bundle member to the repository whose
catalog discovered it (`--to` stays the single-component override).
`GithubReleaseRepository.deploy` no longer rewrites a catalog — the
component is already discoverable through its source catalog; deploy only
publishes the version.

### Step 4 (done) — catalog mapping + repository-local releases.yml (delta)

Step 3 turned the catalog into a location list and made the remote index
fetch one `component.yml` per location. That scaled with the number of
offered components: a working install of a bundle from 8 public sources
needs more than the anonymous GitHub core API budget (60 requests/hour)
in a single run. This step keeps everything `.yak/`-owned unchanged, but
changes **discovery shape** and **release resolution**:

> The catalog **discovers**: a mapping `name → location`. The catalog key
> is a discovery binding / index key — never a normative identity.
> `releases.yml` **resolves**: the published artifact a repository
> currently offers. `component.yml` **owns** identity and version.

#### 1. `catalog.yml` is a mapping again

```yaml
# runtime/catalog.yml
components:
  y5n-runtime-api:
    location: packages/runtime-api
  y5n-runtime-engine:
    location: packages/runtime-engine
```

The component name in the catalog is **only a discovery binding / index
key** — the index resolves by it without reading the component's own
manifest. `.yak/component.yml` remains the sole normative source for
identity and version; the catalog still never declares a version, a
release, a digest or a distribution. Remote discovery performs **no
eager `component.yml` fetch per location anymore** — the remote index is
built in O(catalogs/repositories), not O(components).

#### 2. Identity is validated at the actual access

The catalog key is not blindly trusted. When a component is actually
materialized the expectation is checked against the component's own
contract, and a mismatch fails loudly and unambiguously:

- **Source materialization:** expected catalog name
  `== .yak/component.yml name`.
- **Artifact materialization:** expected resolved name
  `== artifact.yml name`.

Local catalogs may validate eagerly purely as extra error detection;
the discovery model itself never depends on it.

#### 3. Repository-local `releases.yml` — the release index

Each repository keeps a `releases.yml` at the same boundary as its
catalog (next to `catalog.yml`; for a `github:owner/repo:path/catalog`
source beside that catalog). First deliberately small contract:

```yaml
# runtime/releases.yml
components:
  y5n-caps-system:
    version: 0.8.0
    tag: y5n-caps-system-v0.8.0
    digest: sha256:…
```

An entry describes the artifact a repository currently offers for a
component. No history, no list of old versions, no version pinning. The
`version` does not identify a unique build — the `digest` identifies the
concrete offered build. Redeploying the same version with the identical
artifact stays a NO-OP; the existing provider policy for changed
artifacts is unchanged. The format is a Yakoon release index; GitHub
details are not pulled into the contract. If the concrete artifact
reference ever needs more than `tag`, that is reported before extending
the registry contract.

#### 4. Resolution over `releases.yml`

The normal remote install path no longer needs the GitHub Releases API
to scan available releases:

```text
catalog.yml
    ↓
component/repository determined
    ↓
releases.yml            → Contents API (same transport as catalogs)
    ↓
version + tag + digest
    ↓
GitHub Release Asset / CDN download
    ↓
digest check
    ↓
artifact.yml identity check
```

Artifact downloads still go through the release asset CDN and count
separately from API discovery.

#### 5. `yak deploy` maintains `releases.yml`

Deploy publishes the release + asset in the source repository (unchanged)
and subsequently updates that repository's `releases.yml` entry for the
component. `catalog.yml` is not modified by deploy. Distribution follows
source, unchanged — no global distribution, no `dists`.

#### 6. Verified end-to-end

Measured against the live public repositories (2026-08-19; all 8 org
sources migrated; the three offered components deployed through the new
release index):

```text
fresh environment, github: sources only, no token, install system+core
  (y5n-caps-system, y5n-runtime-api, y5n-sdk-python):

  Catalog reads           8   (over the Contents API, one per source)
  releases.yml reads      3   (only the 3 installed components' repos)
  component.yml GETs      0   (no per-location discovery)
  /releases API scans     0   (release resolution entirely over releases.yml)
  Artifact downloads      CDN (digest-guarded cache; 0 re-downloads on reuse)

  pip check               clean
  yak update ×2           stable (no drift, no network within TTL,
                          created timestamp preserved)
  dists                   not involved anywhere
```

Remote discovery and release resolution scale with repositories/catalogs —
the number of available components is out of the cost model.

### Legacy release history

The old `y5n-packs-*` releases in the `dists` repository are legacy and
are **not migrated**. After ADR-23 + distribution, releases are created
fresh in the component repositories (`caps-system/releases/`), starting
with the then-current component version. No historical release migration
is required:

```text
OLD  dists/releases/y5n-packs-*
──── architecture boundary ────────
NEW  <component repo>/releases/y5n-caps-*
```

### Open, implementation-level questions

- `structure/.yak/yak.yml` describes a **node in the Yakoon filesystem**,
  not the component, and is out of this ADR's scope entirely.
- A future `yak component init` would only need to produce the `.yak/`
  contract (component.yml + mount.yml) — no language scaffolding. This
  ADR does not decide whether or when such a command exists.

## Open question

> Where does a Yakoon component describe itself, independent of its
> implementation language?

This ADR answers: **in `.yak/` at the component root — the portable
Yakoon contract of a component, with `component.yml` (name, version)
and `.yak/mount.yml` (structure deployment) as its first contents.**
Steps 1–4 are implemented: the component owns identity and version, the
catalog discovers by a `name → location` mapping, releases resolve over
the repository-local `releases.yml` (no Releases-API scan), and
distribution follows the catalog's source.