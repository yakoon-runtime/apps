# ADR 23: Component Self-Description — Where a Yakoon Component Tells Its Own Story

**Status:** Accepted
**Date:** 2026-08-17

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
component that may know a version at all. Both have since been resolved:
identity/version now live authoritatively in `.yak/component.yml`
(Steps 1–2 below), while the distribution question stays open (Step 3).

## Audit finding

### Metadata files at the component boundary

| File | Level | Content | Language-dependent |
|------|-------|---------|--------------------|
| `pyproject.toml` | component | name, version, deps, build-system | **yes (Python)** |
| `.yak/mount.yml` | component | `path = "/usr/bin"` | no |
| `catalog.yml` | repo / bundle | `components: <name> → location`, `bundles:` | no |
| `structure/.yak/yak.yml` | component structure | tree behavior: title, stores, resolvable, host, entry | no |
| `artifact.yml` | built artifact | name, version, kind, builder, host, mount, fingerprint | partially |
| `sources.toml` / `context.toml` | context | `sources`, `distribution` | no |
| `pack.toml` | — | does not exist anymore (ADR-8 → native identity) | — |

### Field classification

- **Identity** — `.yak/component.yml name` (authoritative since Step 2,
  read in manager `_read_component`) · `catalog.yml` key (duplicate,
  verified against component.yml → `CatalogIdentityError`) · `artifact.yml
  name` (copy).
- **Version** — `.yak/component.yml version` (authoritative since Step 2;
  the build validates the wheel against it) · `catalog.yml release:`
  (dead) · `artifact.yml version` · release tag `{name}-v{version}`
  (derived).
- **Discovery** — `catalog.yml → components.<name>.location` (only source,
  ADR-20; no directory scanning).
- **Build** — `pyproject.toml [build-system]` (Python-specific) ·
  builder discovery finds pyproject.toml only (`_find_buildable_projects`).
- **Distribution** — `context.toml` / `sources.toml` global
  `distribution` (single repository for all components today).
- **Structure/Mount** — `.yak/mount.yml → path` · `structure/.yak/yak.yml`
  (tree behavior, lives inside the mounted structure, not at the repo
  root).
- **Bundle** — `catalog.yml → bundles`.

### The two real duplications

1. **Identity-key** — the catalog must know the name to use it as a key,
   and the component repeats it in pyproject.toml.
2. **Version** — one number in up to five places; the catalog's
   `release:` entry is an unmaintained fifth copy.

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

### 5. Per-component distribution in the catalog

Distribution is **not** an intrinsic property of a component — the same
component may be mirrored or published to several targets. It is a
property of the *catalog entry*: where the component can be obtained
from.

```yaml
# catalog.yml
components:
  - location: .
    distribution: github:yakoon-runtime/caps-system
```

```yaml
# another catalog, same component, different target
components:
  - location: .
    distribution: gitlab:acme/caps-production
```

- The catalog registers where its components are published and resolved;
  each component declares its own target. A private company component
  releases where it lives. No global distribution repository.
- Same inline spec already serves both sides: `fetch_github_release` and
  `GithubReleaseRepository` parse `github:owner/repo` through the same
  `_split_spec`.
- As a consequence, the global `distribution` in `context.toml` /
  `sources.toml` and the `dists` repository are removed.

The full model:

```text
COMPONENT
<component>/.yak/
├── component.yml           name, version
└── mount.yml              structure deployment

REPOSITORY / DISCOVERY
catalog.yml                 location, distribution, bundles

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
- **Migration.** Done in Steps 1–2: every component root now carries
  `.yak/component.yml` and `.yak/mount.yml`; catalogs still carry the
  dead `release:` entries until Step 3; tags move from `dists` to each
  component repository in Step 3.
- **Identity verification.** The catalog key still double-checks identity;
  the builder verifies the native build against component.yml. A
  mismatch between component.yml and the native build metadata is a
  build error.

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
`.yak/component.yml` (`_read_component`, formerly `_read_pack`) and
validates it against the catalog key (`CatalogIdentityError`).

### Step 3 (open) — catalog and distribution

Catalog shape, per-component distribution, the dead `release:` fields,
the global `distribution` and the `dists` repository are all untouched
— they belong to the next step and are removed or reshaped in one
coherent commit.

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
- How `distribution` in a catalog entry is validated against the
  transport it names.
- A future `yak component init` would only need to produce the `.yak/`
  contract (component.yml + mount.yml) — no language scaffolding. This
  ADR does not decide whether or when such a command exists.

## Open question

> Where does a Yakoon component describe itself, independent of its
> implementation language?

This ADR answers: **in `.yak/` at the component root — the portable
Yakoon contract of a component, with `component.yml` (name, version)
and `.yak/mount.yml` (structure deployment) as its first contents.**
Identity and version ownership are implemented (Steps 1–2); catalog and
distribution follow in Step 3.