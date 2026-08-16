# ADR 6: Launcher Responsibilities

**Status:** Accepted

## Context

Yakoon has a working distribution pipeline. `y5n-apps-yak` exists as a
published artifact on GitHub Releases, installable via `install --repository`.

The `yakoon` package on PyPI is currently a stub. It should become the
**Launcher** — the only component permanently delivered via an external
package manager. Everything else distributes through Yakoon itself.

## Architecture

```
PyPI (external)
    │
    ▼
y5n-launcher (Stage 0)
    │
    ├─ 1. Is y5n-apps-yak installed?
    ├─ 2. If not: install from repository
    └─ 3. Forward all arguments
    │
    ▼
Repository (GitHub Releases)
    │
    ▼
y5n-apps-yak
    │
    ▼
Yakoon Platform (runtime, packs, apps, ...)
```

**PyPI ends at the Launcher. Everything below is Yakoon.**

`y5n-launcher` is the only component ever delivered via an external
package manager (PyPI, apt, brew, ...). All other Yakoon components
distribute through Yakoon's own pipeline: `build → publish → install`.

## Naming

The Launcher lives in its own namespace: **`y5n-launcher`**. It is a
first-class Yakoon application — the one that starts all others. Like
pioneers in an army, it belongs to the platform even though its task
is different.

```
launcher/y5n-launcher/       ← namespace: y5n.launcher
    src/y5n/launcher/
        launcher.py

apps/y5n-apps-yak/           ← the actual CLI
runtime/y5n-runtime-*/        ← runtime libraries
packs/y5n-packs-*/            ← content packs
```

## Decision

### What the Launcher is

The Launcher is a **Stage 0** component. Its sole responsibility:

> Ensure the default Yakoon application is available, then launch it.

### What the Launcher does

```
main()
    │
    ├─ Is y5n-apps-yak installed?
    │   YES → forward all arguments
    │   NO  → install from repository → forward
    │
    ▼
subprocess: python -m y5n.apps.yak.hosts.cli.main [args...]
```

The Launcher exposes the `yak` command, but **delegates all command
processing** to `y5n-apps-yak`. From the user's perspective `yak` is
a CLI. Architecturally it is a delegate.

The Launcher explicitly does NOT contain:
- Commands (`build`, `install`, `sync`, `shell`, ...)
- Parser (no argparse, no subcommands)
- Runtime knowledge (no context, workspace, environment, nodes)
- Repository protocol logic (it reads a config file)
- Update logic (version resolution, fingerprints, reconciliation)

ALL of these belong in `y5n-apps-yak`.

### Launcher Configuration

The Launcher ships with a single configuration file:

```yaml
# launcher.yml (bundled in the PyPI package)
repositories:
  - github:yakoon-runtime/apps

default_application:
  name: y5n-apps-yak
```

The Launcher reads this file. It does not interpret the repository URL.
It passes it to a bundled minimal installer that:
1. Resolves the latest release from the repository
2. Downloads the artifact tar.gz
3. Extracts and pip-installs the wheel
4. Records the installation

### Interface to y5n-apps-yak

```python
subprocess.run([
    context_venv_python,
    "-m", "y5n.apps.yak.hosts.cli.main",
    *sys.argv[1:],
])
```

All arguments are forwarded unchanged.

### Evolution rule

The Launcher must never grow new responsibilities. Any code that
implements a "feature" belongs in `y5n-apps-yak`. The Launcher's only
path to evolution is:

> Ship a new version of y5n-apps-yak via the repository.

The Launcher itself is frozen after its initial release. New CLI
features, new commands, new runtime versions — all ship via
`yak publish`, never via PyPI.

### Distribution boundary

| Component | Distributed via |
|-----------|----------------|
| `y5n-launcher` | PyPI (external package manager) |
| `y5n-apps-yak` | Repository (Yakoon's own pipeline) |
| `y5n-runtime-*` | Repository |
| `y5n-packs-*` | Repository |
| `y5n-apps-*` | Repository |

This is the only exception to the "everything is an artifact" rule.
Without it, there is no first component to bootstrap the rest.

## Consequences

### Benefits

- The Launcher is ultra-stable (≈100 lines, never changes)
- The CLI evolves freely in y5n-apps-yak
- Version 5.0 ships via `yak publish`, not PyPI
- The Launcher has zero knowledge of the platform
- Security boundary: Launcher is Python-only; platform is language-neutral
- Single point of distribution: only the Launcher ever needs PyPI

### Trade-offs

- The Launcher bundles a minimal artifact resolver (≈60 lines duplicated
  from y5n-apps-yak). This is intentional — frozen code has no
  maintenance cost.
- First install requires network access to GitHub Releases.
- The repository URL is hardcoded in the launcher configuration.
- The Launcher is Python-specific; non-Python platform access requires
  a different Launcher implementation in the future.
