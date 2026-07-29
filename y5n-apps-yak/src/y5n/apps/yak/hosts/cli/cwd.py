from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Context:
    """A YakContext — the root of a development environment.

    Loaded from .yak/context.toml. Provides roots for resolving
    packs, runtime, apps, and other components.
    """

    path: Path
    name: str = ""
    schema: str = "1"
    root_paths: list[Path] = field(default_factory=list)

    def resolve_roots(self) -> list[Path]:
        paths = list(self.root_paths)
        # Always include the context path itself
        if self.path not in paths:
            paths.append(self.path)
        return [(self.path / r).resolve() if not r.is_absolute() else r for r in paths]

    @staticmethod
    def current() -> Context | None:
        root = find_context_root()
        if root is None:
            return None
        return _load_context(root)

    def __repr__(self) -> str:
        return f"Context({self.name or self.path.name})"


def _load_context(root: Path) -> Context:
    ctx_file = root / ".yak" / "context.toml"
    if not ctx_file.exists():
        return Context(path=root, name=root.name)

    import tomllib

    with open(ctx_file, "rb") as f:
        data = tomllib.load(f)

    ctx_data = data.get("context", {})
    roots_section = data.get("roots", {})
    raw_roots = roots_section.get("dirs", [])
    root_paths = [Path(r) for r in raw_roots] if isinstance(raw_roots, list) else []

    return Context(
        path=root,
        name=ctx_data.get("name", root.name),
        schema=ctx_data.get("schema", "1"),
        root_paths=root_paths,
    )


def default_roots() -> list[Path]:
    """Fallback: monorepo paths relative to this source file."""
    root = Path(__file__).resolve().parents[8]
    return [root / d for d in ("packs", "runtime", "apps", "sdk", root)]


def find_installation_from_cwd() -> str | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        state = parent / ".yak" / "state.toml"
        if state.exists():
            import tomllib

            with open(state, "rb") as f:
                data = tomllib.load(f)
            return data.get("installation", {}).get("name")
    return None


def find_context_root() -> Path | None:
    cwd = Path.cwd()
    found: Path | None = None
    for parent in [cwd, *cwd.parents]:
        if (parent / ".yak" / "context.toml").exists():
            found = parent
    return found


def find_installation_path() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".yak" / "state.toml").exists():
            return parent
    return find_context_root()


def default_artifact_dir() -> Path | None:
    ctx = find_context_root()
    if ctx is None:
        return None
    d = ctx / ".yak" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d
