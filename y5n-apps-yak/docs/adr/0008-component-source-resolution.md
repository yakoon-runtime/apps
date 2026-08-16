# ADR 8: Component Source Resolution — Environment (WHAT), Context (WHERE), State (IST)

**Status: Accepted**

The monorepo is a convenience, not an architecture. Before Yakoon can be
split into independent repositories it needs a distribution model where the
platform itself is resolved through the same mechanisms as any pack. This
ADR defines how a component is resolved: **the Environment declares what
should run, the Context declares where each thing comes from.**

> **A component's origin is a mapping, not a mechanism.** A source mapping
> overrides released resolution; reconciliation turns Environment + Context
> into State.

## Model — six assertions

1. **Environment declares WHAT.**
2. **Context declares WHERE.**
3. **`[sources]` maps a component explicitly to a development source.**
4. **A source mapping overrides released resolution.**
5. **Without a source mapping, the Environment pin is resolved as an
   artifact from repositories.**
6. **Reconciliation turns Environment + Context into State.**

Everything below follows from these six assertions.

## Vocabulary

> **Environment** — WHAT. Declares which components belong to a platform and
> their versions. Shared and versioned; never changed by local work.

> **Context** — WHERE. The machine- and workspace-specific configuration used
> to resolve and operate an Environment. Contains `[sources]` (per-component
> overrides) and `[repositories]` (named artifact sources); later other
> settings. Not merely a "deviation" — it is the setting in which an
> Environment is materialized.

> **State** — IST. What was actually materialized, per component:
> `mode: source | artifact`.

> **Source mapping** — an explicit `[sources]` entry: **one component → one
> development source**.

> **Repository** — a named artifact source: **N components → one artifact
> source**.

## Context

### The monorepo is the last hardcoded coupling

`_build_manager()` derives `sdk_path`, `apps_root`, `runtime_root` and
`packs_root` from `Path(__file__).resolve().parents[8]` — the monorepo. A
released standalone `yak install` has no such paths; the platform cannot be
obtained from anywhere. Before the monorepo can be dissolved, the platform
must be obtainable through the same repository mechanism as packs.

### Three development levels must survive the split

1. **Yakoon core developer** — Runtime, SDK and packs as sources.
2. **Pack developer** — released platform plus one pack as source; must be
   able to check out *only* their own pack and debug against a released
   installation.
3. **User** — everything released.

The central acceptance criterion: after the split, a developer must still be
able to start the runtime in an IDE debugger and set breakpoints in one or
more local source packs. The executed payload must be the checkout.

### Discovery was considered and rejected

A natural idea is to *discover* components inside a source root (walk for
manifests, a `source.yml` at the repo root, per-unit identity files). It was
rejected: discovery is a mechanism Yakoon must implement, test, and debug.
An explicit mapping is one line of configuration.

> **Explicit configuration over clever discovery.** — "Flows are explicit,
> never magical."

## Decision

### 1. `[sources]` is a plain mapping — the common case is the simplest

`path` is the only decided location type. The mapping is therefore a bare
component → path, no wrapper:

```toml
# .yak/context.toml
[sources]
crm = "../crm"
ident = "../ident"
runtime-engine = "../runtime/y5n-runtime-engine"
```

Later types fit the same shape without a model change:

```toml
crm = { git = "git@github.com:acme/crm.git", ref = "dev" }
```

TOML allows both forms side by side. Keys accept the short name (`crm`) and
the fully-qualified name (`y5n-caps-contacts`).

### 2. `[repositories]` stays a separate section — a real cardinality boundary

A source mapping is **1 component → 1 development source**; a repository is
**N components → 1 artifact source**. These are genuinely different
cardinalities, not a stylistic distinction:

```toml
[repositories]
official = "github:yakoon-runtime/apps"
```

Repositories are not pressed into the same vocabulary as development
sources. The ontology stays small: *component → development source* and
*component (unmapped) → repositories → artifact*.

### 3. One pipeline: Environment → Resolve → Reconcile → State

There is **one** resolution mechanism:

```
             Environment
                  │
                  ▼
               Resolve
                  │
                  ▼
              Reconcile
                  │
                  ▼
                State
```

The verbs do not each own a resolution path; they only manipulate the
input:

```
install    → materialize the (initial) Environment
add        → extend the Environment, then re-resolve + reconcile
update     → re-resolve + reconcile
bootstrap  → development setup (venv, context init) — at most a convenience
```

The **Context decides origin, not the verb**: `[sources]` entries produce a
source installation, their absence produces an artifact installation — for
`install` no differently than for `add` or `update`. `bootstrap` is not a
distinct resolution semantic; it may collapse into a convenience workflow
around the same pipeline.

### 4. Source wins unconditionally

A mapped component overrides the Environment version pin. No version
comparison: the developer is working on the *next* version. The Environment
keeps saying `crm = 0.8.0`; the Context says "for my current work, take CRM
from here."

### 5. Removing the mapping restores the released world

```
# crm = "../crm"            ← removed
yak update                  → CRM resolves as the artifact the Environment pins
```

The override is not a second truth: the artifact is still published, the
Environment is unchanged, and the component still carries its build-time
identity (`pack.toml`).

### 6. The language seams are untouched

A source mapping is language-neutral: it says *where*, never *how*. The
language seams — Builder, Installer, Executor — know what to do with the
payload (Python: editable install; later .NET/Go: build output). Debugging
hangs on the same seams: because the executed payload *is* the checkout, the
IDE debugger (Python Debugger, Rider, Delve, Node Inspector) attaches to a
process running development code. Yakoon orchestrates; the ecosystem
develops and debugs. No Yakoon debugger is built.

### 7. Invariant

> When a component runs in source mode, its development payload executes —
> never a released artifact of the same component.

Enforced by the Installer (editable install / symlink), not by the runtime:
`yak runtime start` launches from the installation's venv, where
source-overridden components were materialized from source.

### 8. Invariant — three independent axes

> **Component type, repository ownership, and Environment membership are
> independent concerns.**

A component's technical type does not determine which repository owns it,
and repository ownership does not determine which Environment contains it.
The installer operates only on Environment membership and resolution.

```
root
  type        = pack
  repository  = runtime
  environment = yakoon:platform

system
  type        = pack
  repository  = system
  environment = user-defined
```

This guards against the obvious fallacy during the repository split —
"`root` is a pack, so it belongs in the packs repository." No: the *type*
describes what a component is, the *repository* describes who owns it, and
the *Environment* describes where it is deployed. The three answers are
derived independently; if one starts to imply another, the split is wrong.

The practical repo rule follows:

> **Repositories are cut by ownership and shared lifecycle, not by component
> type.**

Two packs may be very different products with different release cycles and
owners — they belong in different repositories. Repositories grouped by
technical kind (`packs/`, `apps/`, `libraries/`) are the anti-pattern; the
Environment may reach across all Git boundaries.

### 9. Invariant — component identities are opaque

> **Yakoon never interprets a component identity.**

A component's name has no meaning to the resolver. `y5n-caps-system` and
`cool-shell` resolve identically — exactly, by name, with no family prefix
constructed from, or stripped from, a short form. Three consequences:

1. **Identity is opaque.** `y5n-*` is a product convention of Yakoon's own
   components, not part of the architecture.
2. **Resolution is exact.** A name resolves to a component with that name or
   to nothing. `add system` finds nothing when the component is named
   `y5n-caps-system`.
3. **Repositories do not interpret identities.** A source root may assume
   `folder == name` (a component lives in `<root>/<name>`), but it never
   derives one name from another.

Host apps are ordinary components: `y5n-apps-shell` resolves as an artifact
like any pack; there is no tool resolver and no hardcoded platform-name list
in the installer.

## Consequences

### Benefits

- **One resolution mechanism.** If `install/add/update/bootstrap` really run
  through one `resolve → reconcile` pipeline, the verbs become thin wrappers
  and the model cannot drift apart. (Whether the code already does this is
  the first implementation check — see Implementation sketch.)
- **One source of truth.** The mapping feeds build, resolve, and debugging —
  no `dirs`, no directory scanning, no naming-convention guessing in the
  resolver.
- **The monorepo dissolves.** `~/dev/yakoon/` with `[sources]` locations for
  runtime/sdk/apps/crm is a development *workspace* of independent Git
  repositories, not a Git monorepo. Git ownership ≠ development workspace.
- **Mixed operation is free.** Source CRM + released Runtime/Ident/System is
  a mapping with one entry — resolution is per component.
- **One mechanism for everything.** Platform and packs share the same
  resolution path; no second distribution mechanism for the platform, no
  Platform Mega-Artifact (the Environment is the bundle).
- **Debugging is unchanged.** Breakpoints in a source pack hit because the
  running process imports the checkout.
- **Dogfooding.** Yakoon develops its own Runtime/CRM through the same
  context locations that ACME uses for `acme-erp`. If the split is usable by
  an external pack developer, it was cut correctly.

### Trade-offs

- **Explicit enumeration.** A full-sources dev context lists each component
  individually. The redundancy is small, confined to local dev files, and
  buys transparency — cheaper than a discovery mechanism.
- **Two cardinalities coexist.** Component sources (1:1) and repositories
  (N:1) are separate concepts on purpose; the resolver distinguishes them.
- **Transition shims remain.** Until the monorepo is dissolved,
  `default_roots()` and `init`'s auto-detection keep working as
  compatibility defaults; `[sources] dirs` in existing contexts must be
  migrated to `[sources]` mappings.

## Open questions

1. **`git` and `url` locations.** The *shape* is decided (`component →
   location`, typed); the *materialization* is not: where the clone lives,
   how `ref` is updated, whether it is cached by fingerprint like
   repositories. Simplest first step: a manual clone + a `path` mapping. Git
   is deliberately **not** part of this ADR's contract.
2. **Where does the first Environment come from?** `yak` carries the
   *bootstrap configuration required to locate* the official default
   Environment — a default environment location and a default repository —
   **not** the Environment itself, and not concrete platform versions. A
   company uses `yak install acme` or `--environment ./production.yml`. The
   official Environment is the default, not a special case.
3. **Is the mapping machine-local?** The Context is the local setting; the
   natural answer is that it is not committed, like the installation
   (ADR-19). Whether some mappings are worth sharing (a team's dev setup) is
   open.
4. **Per-component repository override.** Should `system = { repository =
   "official" }` be allowed — a component naming a *specific* repository
   instead of the general list? This crosses the cardinality boundary and is
   deliberately undecided.
5. **Environment schema.** This ADR treats the Environment as "components
   with versions" (cf. ADR-3); the exact schema is out of scope here.

## Implementation sketch

Implemented and proven end to end (gold tests A–D in
`apps/y5n-apps-yak/tests/test_source_resolution.py`):

1. **Context** reads `[sources]` as a `component → location` map and
   `[repositories]` as named repositories (`cwd.py`). `dirs` stays as a
   build-time transition shim.
2. **One resolver.** `_resolve_component` (manager) consults the Context
   mapping first, then the artifact repositories (defaulting to the
   Context so `add` and `update` always agree). `_resolve_platform_component`
   is gone — root/boot resolve like every component, through a mapped
   development source or the artifact repositories (`naming=False` keeps
   the name-based fallback out of the platform namespace).
3. **Installer** reuses the existing editable-install and structure-symlink
   path for `path` mappings.
4. **`add`** passes only CLI overrides; the resolver owns the Context
   default. **`update`** uses the same default — one source of truth.
5. **Gold tests** prove the core of the ADR:

   ```
   A — Released        no mapping            → crm artifact, staged copy
   B — Dev override    crm → ../crm          → crm source, payload = checkout
   C — Return          mapping removed       → crm artifact, symlink gone
   D — Platform        root/boot as artifacts→ install without parents[8]
   ```
