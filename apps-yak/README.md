# yak — Yakoon CLI

`yak` is the command-line tool for Yakoon — it owns *installation* and
*distribution* (assemble an environment, build/publish/deploy components).
`yak` is a **tool / assembler**: it does not own what a component is, what
it delivers, or how it runs. Those belong to each component's own
`.yak/` contract (`component.yml`, `mount.yml`) and to the runtime.

Yakoon starts empty. One composition primitive makes a component or a
bundle part of an environment:

    yak install <component|bundle> [--path <catalog>]...

The first argument is always an identity: a component name or a bundle
name. A bundle is a name → list of component names; it resolves to its
members through the shared index.

## Discovery, resolution, authority

Three owners, cleanly separated:

| File | Owner | Answers |
|------|-------|---------|
| `catalog.yml` | repository | `name → location` (discovery) |
| `releases.yml` | repository | offered artifact (`version + tag + digest`) |
| `.yak/component.yml` | component | identity + version (authority) |
| `.yak/mount.yml` | component | delivery (`source → path`) |

A catalog (`catalog.yml`) is what a source offers. It is a `name →
location` mapping — the key is a discovery binding / index key only, never
a normative identity. Identity and version live in each location's
`.yak/component.yml`, and the currently offered artifact of each component
resolves through the repository-local `releases.yml` at the same boundary
as the catalog (ADR-23):

```yaml
# catalog.yml
components:
  y5n-runtime-api:
    location: packages/runtime-api
  y5n-runtime-engine:
    location: packages/runtime-engine

bundles:
  runtime:
    - y5n-caps-root
    - y5n-runtime-api
    - y5n-sdk-python
```

`location` answers *where the component is*; the component declares *who
it is* in its own `.yak/component.yml`. The catalog key is validated
against that declaration at the actual materialization — a mismatch fails
loudly. Bundles are global — they name components and resolve through the
shared index, first hit wins.

```yaml
# releases.yml — what a repository currently offers
components:
  y5n-caps-system:
    version: 0.8.0
    tag: y5n-caps-system-v0.8.0
    digest: sha256:…
```

`yak deploy` publishes the release and updates the repository's
`releases.yml`. Remote resolution reads catalogs and `releases.yml` over
the Contents API only — it never scans the GitHub Releases API, so
discovery and release resolution scale with repositories, not with the
number of offered components.

## Mount — what a component delivers where

A component delivers into the tree only when it declares it, in
`.yak/mount.yml` as an explicit `source → path` mapping (no hard-coded
directory name). The component owns this declaration; `yak` only honors
it during materialization:

```yaml
# .yak/mount.yml
source: structure        # component-relative directory to mount
path: /usr/bin           # its target in the materialized tree
```

No `mount.yml` means the component delivers nothing into the tree (a pure
library). The `source` directory is the deliverable and may be any
component-relative path the project chooses — there is no imposed layout
outside `.yak/`:

```yaml
# a .NET component mounting an idiomatic folder
# .yak/mount.yml
source: yakoon/commands
path: /usr/bin
```

## Compose an environment

    yak install system          # the system bundle, from releases
    yak install crm             # one component, from its release
    yak install crm --path ./my-catalog

`--path` is a repeatable **source override**: it points at a source with
a `catalog.yml` (never directly at a component). A component found in
any `--path` catalog resolves through its `location` (source); everything
else resolves through its `release` (artifact) — per component, no global
mode. An installation can hold `runtime-api = source` and
`sdk-python = artifact` at the same time.

Granularity:

    yak install runtime
    yak install runtime --path ./runtime --path ./sdk --path ./apps

The last form resolves every member of the `runtime` bundle as a source.

## Where a component lives in an installation

`install` stages each component's namespace into the installation-local
component store, at a version-stable path:

    .yak/components/<name>/structure

A source component is a symlink into its source tree (editable); an
artifact component is copied (self-contained). The materializer never
reads from artifact stores or language packages — component namespaces
are staged through `.yak/components/<name>/structure` first.

`environment.yml` lists the desired components (SOLL); `state.toml`
records what is installed and why (IST: mode, version, fingerprint,
source). `yak update` reconciles the two. Installing an identity on an
existing environment adds its components; `install` returns nothing when
the identity is already part of the environment.

## Build and distribute a component

`yak` builds a component from its own `.yak/component.yml` identity, then
publishes it. Distribution follows the source — a component deploys to the
repository whose catalog discovered it:

    Source
      │ build
      ▼
    .yak/artifacts/
      │ publish
      ▼
    ~/.yak/artifacts/
      │
      │ deploy
      ▼
    Repository
      │
      └── install ──→ Other installation

`build` produces artifacts from a project; `publish` lifts a built
artifact into the system-global store; `deploy` ships a *published*
artifact into the source repository of the component, updating
`releases.yml` so other installations resolve it immediately:

    yak build acme-erp
    yak publish acme-erp
    yak deploy acme-erp --to github:acme/packs

Any installation can then resolve the component from that repository:

    yak install acme-erp

Credentials come from the environment, never from configuration files:

    export YAK_GITHUB_TOKEN=<token>

`deploy` needs permission to create releases in the target repository: a
fine-grained token requires **Contents: Read and write** for that
repository; a classic token requires the `repo` scope. Tokens are never
stored in `.yak/` configuration.

## The model

    install    makes a component or bundle part of an environment
    context    defines where components are found
    build      builds a component
    publish    makes a component available on this system
    deploy     makes a component available outside this system
