# ADR 19: Declarative Deployment

**Status: Accepted**

ADR-18 proved that a pack can declaratively describe the logical stores it
uses, without knowing infrastructure. This ADR answers the second half of
the story: **how does a collection of declarative packs become a running
installation?**

The answer is the **installation** — the machine-specific product of the
assembler. `yak` collects the stores the installed packs declare and
materializes an installation that binds each store to a **StoreFactory**
(a Python import path) and an opaque config. The runtime reads the
installation, materializes every store through its factory, and routes
`store.get("crm")` to the store the installation built. There is no
default store and no runtime without an installation.

> **A pack declares the stores it uses. `yak` assembles the installation.
> The runtime routes the bound name to the store the installation built.**

## Key sentence

> **`stores:` describes dependencies and their scope, not authorization.**
>
> A pack declares the store capabilities it uses. `yak` assembles them
> into an installation. At runtime a bound name routes to the store the
> installation built — no more, no less.

## Vocabulary

> **Store** — a logical, named capability (`crm`, `runtime`). The name is
> the binding: the runtime routes `store.get("crm")` to the physical
> store the installation built for `crm`.

> **StoreFactory** — the only component that knows how to build a
> physical store. A factory is referenced by Python import path
> (`y5n.runtime.store.event.wire:EventStoreFactory`) and owns its config
> language: where a DSN comes from (a literal string, `env://NAME`, ...)
> is storage knowledge, not runtime knowledge. `build(config)` returns a
> complete **StoreRuntime**.

> **StoreRuntime** — one physical store: entity `objects` **and** its
> `sequencer`, plus lifecycle. Sequencing is part of the storage
> semantics; the runtime never marries a store to a sequencer itself.

> **Installation** — the machine-specific product of the assembler:
> `.yak/deployment.yml`, owned by `yak` and the operator, not versioned.
> Each store is bound directly to a factory and config — there is no
> named deployment registry in between. Consumed by the runtime at
> startup.

> **Assembler** — the role of `yak`: it collects the declared stores of
> all installed packs and materializes the installation that satisfies
> them.

## Context

### ADR-18 ended at the pack

ADR-18 proved the chain from `stores:` to `sdk.store("crm")` with no
infrastructure knowledge in the packs. What it did **not** answer is where
the physical stores come from. Today persistence ran on engine defaults
(`settings.storage`, a silent memory fallback) — an implicit store owned
by no one.

### Two axes, not one

The key question — *is a logical store globally unique?* — resolves into
two separate axes:

| Axis | Answer |
|---|---|
| Meaning of the name | global — `crm` is `crm` everywhere |
| Permission to access | pack-local — a pack declares the stores it uses |

A name collision is deliberate sharing (two packs declaring `crm` share
the one store, ADR-17). Access is granted by declaration — a pack can
only *use* the stores it declares, and `sdk.store(name)` binds to the
store the installation built.

### Runtime enforcement is not authorization

`stores:` is not a security boundary against the pack author — the pack
author controls their own YAML. Its runtime value is correctness and
transparency (an unbound name is an error), not protection. There is no
per-call node check: a bound `store.get("ident")` routes to `ident`
regardless of who happens to call through a port. The declaration is the
*assembler's* input, not a per-call gate.

## Problem

1. **Persistence was configured, not deployed.** DSNs and backends were
   engine settings, and an implicit memory fallback hid their absence.
2. **No one answered "which database exists?"** The mapping from logical
   store to physical resource had no owner.
3. **Store and database were conflated.** The platform must keep them
   apart, or the model collapses into "a store is a postgres".
4. **The runtime was a factory for all storage types.** Backend and
   credential schemes lived in the runtime bootstrap; adding a database
   meant changing the runtime.

## Decision

### 1. Store ≠ Database

A **store** is logical and globally meaningful; a **database** is physical
and deployment-local. Multiple logical stores may map to one physical
resource; one logical store maps to exactly one factory binding.

```
crm ──────┐
           ├──► EventStoreFactory + postgres DSN
ident ────┘

runtime ────► EventStoreFactory + memory
```

### 2. The installation binds directly — no deployment registry

The pack declares names only. The installation decides, **per store**,
which factory and config materialize it:

```yaml
# .yak/deployment.yml
stores:
  runtime:
    factory: y5n.runtime.store.event.wire:EventStoreFactory
    config:
      backend: memory

  crm:
    factory: y5n.runtime.store.event.wire:EventStoreFactory
    config:
      backend: postgres
      dsn: env://CRM_DATABASE
```

There is no `deployments:` level and no named deployment registry: a store
is bound directly to its factory. Two stores with the same factory and
config share one physical instance.

### 3. The factory owns the config language

The runtime does not know `memory://`, `postgresql://`, `env://` or any
credential scheme. `build_store_registry` loads the factory by import
path and calls `build(config)`. The factory decides what its config means
— a `dsn` may be a literal connection string or a reference the factory
resolves. New storage types mean a new factory, never a runtime change.

### 4. `stores:` is a dependency declaration

A pack declares the stores it uses, once, at the pack root:

```yaml
stores:
  - crm
```

`yak` collects these declarations and assembles the installation. At
runtime the SDK binds `store.get("crm")` and the runtime routes the name
to the installed store. There is no default store and no per-call
enforcement: an unbound name is an explicit "not installed" error.

### 5. `runtime` is a normal store capability

The runtime's own infrastructure — session, activity — needs persistence.
It requires a store named `runtime`, declared by the system pack and
materialized by the installation like any other. `runtime` is **not a
default**: the resolver never falls back to it, and no pack reaches it
without declaring it. Its peculiarity lies only in *who requires it*.

### 6. The product is an installation, not runtime configuration

`yak` writes **no configuration for the runtime.** It writes an
**installation** — the machine-specific product of the assembler, kept
outside Git at `.yak/deployment.yml`. The workspace owns its private
state in `.yak/`; the assembled structure tree stays separate and
regenerable. A notebook maps `crm` to memory, a server maps it to a
postgres cluster — same pack, same runtime, a different installation.

## Consequences

### Benefits

- **The runtime knows no storage schemes.** Backend and credential
  knowledge live in the factory; the engine holds none.
- **The installation is the only place that binds stores.** One mapping,
  one owner (the operator via `yak`).
- **One materialization source.** `settings.storage`/`sequencer` are
  gone; every physical store — including `runtime` — comes from the
  installation.
- **No default, no fallback.** An unbound name fails loudly.
- **The platform grows.** The same model later covers queues, caches,
  search — each a capability with a global name, bound by the
  installation.

### Trade-offs

- **The runtime still knows its own store by name.** `build_runtime`
  resolves `registry["runtime"]` to wire its persistent services. That is
  identity, not implementation: the runtime must find *its* store, but
  knows nothing about its technology.
- **A bound store needs a factory import path.** The installation
  references Python; the store layer is Python-internal by design.

### Strong test (direction)

The end state is:

> `build_runtime()` materializes the store registry, but never consumes a
> store itself.

Today it still touches `registry["runtime"]` for `SessionService` and
`ActivityService`. The follow-up is to let those services resolve their
store dependency themselves (like any port provider), so even that
coupling disappears.

## Open questions

The open questions are not leftovers — they define the platform. Ordered
by dependency:

1. **How does `yak install` guide the mapping?** The assembler asks the
   operator which factory and config each declared store gets — new or
   existing, which database, where the DSN comes from. It never searches
   databases and knows no naming conventions; the operator knows more
   than the tool.
2. **Where do credentials live?** A `dsn` reference (`env://NAME`, later
   a secret store) is factory knowledge. The installation may carry
   references; the secret itself lives outside the pack and the
   installation.
3. **Who owns migrations?** The pack — it knows its data model; `yak` and
   the runtime do not. `yak` only *executes* migrations; migration status
   becomes part of the installation.
4. **What happens on update / uninstall?** `yak update` asks only for
   newly declared stores; existing bindings stay untouched. Uninstalling
   never deletes data — at most a warning that a store is no longer
   referenced.
5. **Who owns the schema of a shared logical store?** Access is settled
   (`stores:` grants it), but evolution is not. Likely the seed of
   ADR-20.

## Implementation sketch

Implemented and proven end to end:

1. **Store model.** `StoreBinding(factory, config)`; the installation
   binds every store — including `runtime` — directly to a factory.
2. **StoreFactory.** `EventStoreFactory.build(config) → StoreRuntime`
   (objects + sequencer). New backends are factories, not runtime code.
3. **Runtime consumption.** At startup the runtime loads the installation,
   materializes the registry through the factories, and routes
   `store.get(name)` to the installed store. No installation → no runtime.
4. **Assembler.** `yak` collects declared stores and writes the
   installation; the interactive mapping (which DB, which secret) is the
   next step.
5. **Tests.** A bound name routes to its store; the same factory and
   config share one instance; a node without a declared store gets an
   explicit "not installed" error; crm on postgres persists across
   restarts.
