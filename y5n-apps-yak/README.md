# yak — Yakoon CLI

`yak` is the command-line interface for Yakoon — a composable,
language-neutral runtime platform.

Yakoon starts empty.

The runtime itself contains no packs, no commands and no product
assumptions. Capabilities are added explicitly with `yak add`.

## Runtime first

A fresh Yakoon platform consists only of the runtime, SDK and host
applications:

    Yakoon Platform
        │
        ├── Runtime
        ├── SDK
        └── Hosts
        │
        └── 0 packs
            0 nodes
            1 store: runtime

Everything else is composed afterwards:

    yak add system
    yak add ident
    yak add crm

`system`, `ident` and `crm` are packs. None of them is implicitly part
of Yakoon.

This means that a perfectly valid Yakoon installation may consist of
only the runtime, or of the runtime plus a company's own packs.

---

## Bootstrap or install?

There are two ways to create the same minimal Yakoon platform.

### `yak bootstrap` — build the platform from source

Use `bootstrap` when you are working inside a Yakoon source repository.

    git clone <yakoon-repository>
    cd <yakoon-repository>

    yak bootstrap

`bootstrap` uses the platform projects from the local source tree and
installs them editable.

It is intended for developing Yakoon itself.

After bootstrap, the platform is deliberately empty:

    0 packs
    0 nodes
    runtime store

Add whatever you need:

    yak add system
    yak add ident
    yak add crm

### `yak install` — install the platform

Use `install` when you want to use or operate Yakoon without developing
the Yakoon platform itself.

    mkdir my-yakoon
    cd my-yakoon

    yak install

`install` creates the same minimal platform from installable platform
artifacts.

Afterwards, compose the installation in exactly the same way:

    yak add system
    yak add ident
    yak add crm

The difference is only where the platform comes from:

                         Minimal Yakoon Platform
                                  ▲
                                  │
                     ┌────────────┴────────────┐
                     │                         │
                yak bootstrap             yak install
                     ▲                         ▲
                     │                         │
                local sources             artifacts
                 (editable)

Once the platform exists, both workflows are identical.

---

## Compose your installation

`yak add` determines what a Yakoon installation can do.

For example:

### Minimal system

    yak install
    yak add system

### CRM system

    yak install
    yak add system
    yak add ident
    yak add crm

### Development from source

    git clone <yakoon-repository>
    cd yakoon

    yak bootstrap
    yak add system
    yak add ident
    yak add crm

A company can just as well build its own composition:

    yak install
    yak add acme-system
    yak add acme-erp
    yak add acme-machines

Yakoon does not require the standard `system`, `ident`, `crm` or any
other product pack.

---

## The tree is the model

Packs are mounted into the Yakoon tree.

For example:

    /
    ├── system/
    │   ├── ls
    │   ├── cd
    │   └── su
    │
    ├── ident/
    │   ├── accounts
    │   └── groups
    │
    └── crm/
        └── contacts

There is no global command pool and no PATH.

Commands are resolved relative to the current node or addressed by
their path.

For example:

    /system/ls

or, when the current node is `/system`:

    ls

`system` is not a privileged `/usr/bin`. It is a pack namespace like
any other.

---

## Typical workflows

### Develop Yakoon itself

    git clone <yakoon-repository>
    cd yakoon

    yak bootstrap
    yak add system

### Use Yakoon

    mkdir my-yakoon
    cd my-yakoon

    yak install
    yak add system
    yak runtime start

### Develop a pack

    yak create pack hello
    cd hello
    yak create command greet

    yak build .
    yak publish y5n-packs-hello

    # Add it to an existing Yakoon installation
    yak add y5n-packs-hello

### Operate an installation

    yak add <component>
    yak update

    yak runtime start
    yak runtime status
    yak runtime stop

    yak shell
    yak doctor

---

## Lifecycle

Yakoon separates platform creation, composition and operation:

    Platform
        bootstrap / install
               │
               ▼
    Composition
              add
               │
               ▼
    Reconciliation
             update
               │
               ▼
    Operation
        runtime / shell / doctor

Or, from a development perspective:

    create → build → publish
                       │
                       ▼
                 yak add
