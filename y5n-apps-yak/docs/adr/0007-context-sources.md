# ADR 7: Context Sources and Repositories

**Status:** Draft for discussion

## Context

The monorepo is a configuration, not an architecture. Yakoon components
should be discoverable through the Context, not through hardcoded paths.

## Principle

> **Das Monorepo sollte keine Sonderbehandlung sein. Es sollte lediglich der Default-Context sein.**

## Architecture

```
CLI
 │
 ▼
Context.current()
 │
 ▼
context.resolve_roots()    → [./packs, ./runtime, ./apps, ...]
 │
 ▼
FileRepository(*roots)
DirectoryArtifactStore(*roots)
```

`roots` are a **capability** of the Context, not its identity. The Context
may grow to provide workspace, repositories, profiles, credentials, and
environment — `roots` are one detail.

## Decision

### 1. Context carries root resolution

`.yak/context.toml` gains an optional section:

```toml
[context]
name = "yakoon"

roots = [
    "packs",
    "runtime",
    "apps",
    "sdk",
]
```

A standalone product repo:

```toml
[context]
name = "crm"

roots = ["."]
```

A workspace combining multiple repos:

```toml
[context]
name = "workspace"

roots = [
    "../yakoon/runtime",
    "../yakoon/sdk",
    "../crm",
    "../luma",
]
```

### 2. Context model

```python
@dataclass
class Context:
    name: str
    schema: str = "1"
    root_paths: list[Path] = field(default_factory=list)

    def resolve_roots(self) -> list[Path]:
        """Resolve root paths relative to the context directory."""
        return [(self.path / r).resolve() for r in self.root_paths]

    @staticmethod
    def current() -> Context | None:
        """Walk up from CWD looking for .yak/context.toml."""
        ...
```

### 3. `_build_manager()` becomes context-based

```python
def _build_manager():
    ctx = Context.current()
    
    roots = ctx.resolve_roots() if ctx else default_roots()
    
    artifact_dir = Path(__file__).resolve().parents[8] / "apps" / "y5n-apps-yak" / "artifacts"
    
    repo = FileRepository(*roots, builtin_artifacts=artifact_dir)
    store = DirectoryArtifactStore(*roots)
    return InstallationManager(repo, store)
```

### 4. `default_roots()` replaces `_detect_monorepo()`

```python
def default_roots() -> list[Path]:
    """Fallback when no context is present."""
    root = Path(__file__).resolve().parents[8]
    return [root / d for d in ("packs", "runtime", "apps", "sdk")]
```

Same behavior as today, but the name says *what* it provides, not *where*.

### 5. FileRepository and DirectoryArtifactStore

Both already accept `*roots`. No changes needed.

## Future: Workspace-level repositories

This ADR keeps roots at the context level. A future step may introduce
a workspace concept that collects multiple repositories:

```toml
[workspace]
repositories = [
    "../yakoon",
    "../crm",
    "../luma",
]
```

Each repository provides its own context with its own roots.
This would require no changes to FileRepository or ArtifactStore —
only an additional layer that aggregates roots from multiple contexts.

## Consequences

### Benefits
- Monorepo is just the default — products in their own repos work identically
- `_build_manager()` no longer knows about directory layouts
- Workspaces can combine multiple repos
- No architectural difference between "core" and "product" components

### Trade-offs
- Existing contexts without `roots` default to monorepo layout
- `default_roots()` stays as a compatibility shim
- Context format needs a schema version for future migrations

### Non-goals
- The Launcher never sees roots — it only installs y5n-apps-yak
- Artifact resolution (Repository protocol) is already flexible
