# ADR 22: The Workspace as a Materialized Filesystem

**Status:** Accepted
**Date:** 2026-08-17

## Context

The workspace tree `.yak/structure` is currently a pure composition of
symlinks that reaches all the way back into the component source
repositories:

```text
caps-worlds/structure                (real files, in the git repo)
  └─ .yak/components/y5n-caps-worlds/structure   → symlink to repo
       └─ .yak/structure/opt/worlds              → symlink to .yak/components/…
```

This has two consequences:

- **There is no place for data.** A file created inside
  `.yak/structure/opt/worlds/` lands physically in the `caps-worlds`
  repository. The workspace is a pass-through, not a real tree.
- **Backups are hollow.** Backing up `.yak/` copies symlinks, not the
  contents they point at.

The component store `.yak/components/<name>/structure` already answers
one question well: *where did this installed structure come from.* The
materialization layer, however, re-points at it instead of building the
structure it is asked to provide.

The next feature (Files: real files in the workspace, links such as
`home/documents` created via an `ln` command, a backup that captures
everything) requires a workspace that is a **real** tree. The design
below keeps the provenance layer and replaces the symlink pass-through
with true materialization.

## Decision

Two layers with distinct responsibilities:

```text
Caps / Packages
      │
      ▼ install
.yak/components/                 Provenance (where it comes from)
      │ structure → source
      │
      ▼ materialize
.yak/structure/                  Reality (the concrete environment)
├── .yak/
├── boot/
├── usr/
├── opt/
├── home/
├── real files
├── real directories
└── real symlinks
```

- **`.yak/components/<name>/structure` remains a symlink** to the
  installed/source structure. This is provenance: it answers *where the
  installed structure comes from.* It is the installation / origin
  mechanism and is not part of the workspace tree.
- **`.yak/structure` is truly materialized**: real directories and
  files, no component symlinks. It is the concrete structure of this Yak
  environment.
- **`caps-root` provides the base structure.** A mount targeting `/`
  identifies that base; all other component structures are overlaid onto
  it (`usr/bin`, `opt/…`, `boot/…`). `/` is not a special mount
  operation — it is the marker of the base. The materializer may copy
  the base first internally, but that is an implementation detail.
- **User/agent files live in the same tree** afterwards, exactly like
  any other content.
- **Links inside the tree are ordinary symlinks**, later created e.g.
  through an `ln` command (`home/documents` → `~/Dokumente`).
- **Cap code runs from `.venv` anyway**; the copied structure does not
  need to reach back into the repository to stay editable.

### The managed rule

`yak update` does not simply "never delete". The rule is:

> **Yak may create, change and remove anything Yak has materialized.
> Everything else in the tree is left untouched.**

A managed entry that a new cap version no longer contains must be
removable on update/uninstall — otherwise the tree accumulates dead
entries. Yak's own materialized set (and the boundary to foreign
content) is an **implementation detail**: `workspace.toml`, the existing
state or a dedicated manifest.

There are **no artificial zones**: the tree is not divided into
`/usr = Yak` and `/home = User`. The only distinction is
managed (Yak may reconcile) vs. unmanaged (Yak leaves it alone).
`/home` may later become a convention for user/agent content — it is not
a materializer special rule.

### Reconciliation

`yak update` reconciles the entries Yakoon has materialized:

- new entries are created,
- changed managed entries are updated,
- managed entries that disappeared from a cap version are removed,
- everything that is not managed stays exactly as it is.

## Implementation Notes

Open, implementation-level questions (not architecture):

- Manifest form: extend `workspace.toml`, keep a separate manifest, or
  use the existing state?
- How the managed set is recognized vs. foreign content (manifest list,
  fingerprint, …).
- Overlay conflict resolution between caps (deterministic order).
- Migration path from an existing symlink workspace to a materialized
  one.

## Consequences

- `.yak/structure` becomes self-contained. A backup of `.yak/` therefore
  contains the complete materialized Yakoon filesystem and its local
  data; provenance links under `.yak/components` may still point outside
  the environment.
- Files and `ln` links have a real home in `.yak/structure`.
- The source-of-truth boundary stays intact: provenance remains in
  `.yak/components`, the workspace never points into repositories.
- Editing a cap is visible in the workspace only after `yak update` —
  accepted, since running code comes from `.venv`.

> **`.yak/components` answers where the installed structure comes from.
> `.yak/structure` is the concrete structure of this Yakoon
> environment.**
