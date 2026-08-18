# yak — Yakoon CLI

`yak` is the command-line interface for Yakoon — a composable,
language-neutral runtime platform.

Yakoon starts empty. One composition primitive makes a component or a
bundle part of an environment:

    yak install <component|bundle> [--path <catalog>]...

The first argument is always an identity: a component name or a bundle
name. A bundle is a name → list of component names; it resolves to its
members through the shared index.

## Sources and artifacts

A catalog (`catalog.yml`) is what a source offers. It lists locations
only — identity lives in each location's `.yak/component.yml`, and
releases are discovered from the source repository (ADR-23):

```yaml
# catalog.yml
components:
  - location: packages/runtime-api
  - location: packages/runtime-engine

bundles:
  runtime:
    - y5n-caps-root
    - y5n-runtime-api
    - y5n-sdk-python
```

`location` answers *where the component is*; the component declares
*who it is* in its own `.yak/component.yml`. Bundles are global — they
name components and resolve through the shared index, first hit wins.

## Compose an environment

    yak install runtime          # the runtime bundle, from releases
    yak install crm              # one component, from its release
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

Yak in one picture:

    Source
      │ build
      ▼
    .yak/artifacts/
      │ publish
      ▼
    ~/.yak/artifacts/
      │
      ├── install ──→ Installation
      │
      │ deploy
      ▼
    Repository
      │
      └── install ──→ Other installation

`build` produces artifacts from a project; `publish` lifts a built
artifact into the system-global store; `deploy` ships a *published*
artifact into a remote repository, where other installations can resolve
it immediately.

    yak build acme-erp
    yak publish acme-erp
    yak deploy acme-erp --to github:acme/packs

Any installation can then resolve the component from that repository:

    yak install acme-erp

Credentials come from the environment, never from configuration files:

    export GITHUB_TOKEN=<token>

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
