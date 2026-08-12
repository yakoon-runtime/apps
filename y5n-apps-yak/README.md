# yak — Yakoon CLI

`yak` is the command-line interface for Yakoon — a composable,
language-neutral runtime platform.

Yakoon starts empty.

The runtime itself contains no packs, no commands and no product
assumptions. Capabilities are added explicitly with `yak add`.

## Install or bootstrap?

Both commands create the same minimal Yakoon platform.

Use `install` for a regular installation:

    mkdir my-yakoon
    cd my-yakoon
    yak install

The platform is installed from released artifacts.

Use `bootstrap` when developing Yakoon itself from a source checkout:

    git clone <yakoon-repository>
    cd <yakoon-repository>
    yak bootstrap

The platform is installed from the local sources (editable).

In both cases the result is a minimal platform:

    Runtime + SDK + Hosts
    0 packs
    0 nodes
    runtime store

The difference is only how the Yakoon platform itself is installed:

    yak install     → released artifacts
    yak bootstrap   → local sources (editable)


## Add components

Components are added with the same command in every environment:

    yak add system
    yak add ident
    yak add crm

`yak add` resolves a component from the sources available to the
current context:

    1. Source directories      [sources] in context.toml
    2. Local artifact store    published artifacts
    3. Repositories            [repositories] in context.toml

The artifact store is always system-global:

    ~/.yak/artifacts/

`build` stages the artifact in the context-local `.yak/artifacts/`;
`publish` lifts it into the system-global `~/.yak/artifacts/`, where
every installation can resolve it.

This allows released and development components to be mixed in the
same installation.

### Where a component lives in an installation

`add` stages each component's namespace into the installation-local
component store, at a version-stable path:

    .yak/components/<name>/structure

A source component is a symlink into its source tree (editable); an
artifact component is copied (self-contained). The workspace
materializes exclusively from the component store — never directly
from a source tree, an artifact store or a language package:

    .yak/artifacts/                  build staging
    ~/.yak/artifacts/                system-wide distribution
    <installation>/.yak/components/  installed state

`environment.yml` lists the desired components (SOLL); `state.toml`
records what is installed and why (IST: mode, version, fingerprint,
source). `yak update` reconciles the two.


### Regular installation

    yak install
    yak add system
    yak add ident

Result:

    Runtime     artifact
    system      artifact
    ident       artifact


### Yakoon development

    yak bootstrap
    yak add system
    yak add ident

Result:

    Runtime     local source (editable)
    system      local source
    ident       local source


### Develop company components against released Yakoon

Start with a regular Yakoon installation:

    yak install
    yak add system
    yak add ident

Then add the company's development directory to the context:

    # .yak/context.toml

    [sources]
    dirs = ["/home/acme/dev/packs"]

Now local company components can be added directly:

    yak add acme-erp
    yak add acme-machines

Result:

    Runtime          artifact
    system           artifact
    ident            artifact
    acme-erp         local source
    acme-machines    local source

The company can therefore develop and debug its own components
against a released Yakoon installation without publishing them first.

When a component is ready for release:

    yak build acme-erp
    yak publish acme-erp
    yak deploy acme-erp --to acme

Other installations can then resolve it as an artifact.

## Distribute a component

The component path to other systems:

    build     → .yak/artifacts/       built for this context
    publish   → ~/.yak/artifacts/     available on this system
    deploy    → repository            available outside this system

`publish` copies a built artifact into the system-global store:

    yak publish acme-erp

`deploy` ships a *published* artifact into a remote repository, where
other installations can resolve it immediately:

    yak deploy acme-erp --to acme

`deploy` reads only from the published store — an artifact must be
published first. It publishes a release, never a draft.

Repositories are configured in the context. A named repository is both a
read source (`add --from`) and a deploy target (`deploy --to`):

    # .yak/context.toml

    [repositories]
    sources = ["github:yakoon-runtime/packs"]

    [repositories.acme]
    type = "github"
    repo = "acme/packs"

    yak add acme-erp --from acme
    yak deploy acme-erp --to acme

An inline spec works without configuration:

    yak deploy acme-erp --to github:acme/packs

Credentials come from the environment, never from configuration files:

    export GITHUB_TOKEN=<token>
    # or: export YAK_GITHUB_TOKEN=<token>

`deploy` uses `GITHUB_TOKEN` (or `YAK_GITHUB_TOKEN`) and needs permission
to create releases in the target repository. Tokens are never stored in
`.yak/` configuration.

## The model

    install/bootstrap    creates the platform
    context              defines where components are found
    build                builds a component
    publish              makes a component available on this system
    add                  adds a component to an installation
    deploy               makes a component available outside this system
