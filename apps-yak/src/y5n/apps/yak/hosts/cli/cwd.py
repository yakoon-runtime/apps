from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Context:
    """A YakContext — describes a development environment.

    Loaded from .yak/context.toml. ``sources`` is the flat ADR-20 source
    set (catalog locations) — where components are discovered. Each source
    repo is also the default distribution of its own components (ADR-23
    Step 3), so no global distribution exists. ``source_dirs`` is a
    transition: the local monorepo folders the installer resolves build
    roots against until the repo split.
    """

    path: Path
    name: str = ""
    schema: str = "1"
    sources: list[str] = field(default_factory=list)
    source_dirs: list[Path] = field(default_factory=list)

    def resolve_sources(self) -> list[Path]:
        paths = list(self.source_dirs)
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
    # ``source_dirs`` is a transition list: the local monorepo folders
    # the installer resolves build roots against until the repo split.
    # It lives top-level so it cannot collide with the flat
    # ``sources = [...]`` (ADR-20) list.
    raw_dirs = data.get("source_dirs", [])
    source_dirs = [Path(r) for r in raw_dirs] if isinstance(raw_dirs, list) else []

    return Context(
        path=root,
        name=ctx_data.get("name", root.name),
        schema=ctx_data.get("schema", "1"),
        sources=_string_list(data.get("sources")),
        source_dirs=source_dirs,
    )


def _string_list(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def find_context_root() -> Path | None:
    cwd = Path.cwd()
    found: Path | None = None
    for parent in [cwd, *cwd.parents]:
        if (parent / ".yak" / "context.toml").exists():
            found = parent
    return found


def find_runtime_root() -> Path | None:
    """Find the nearest ancestor holding a runtime root.

    A runtime root is a directory with a Yak context or an installation:
    ``.yak/context.toml``, ``.yak/state.toml`` or ``.yak/environment.yml``.
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        yak = parent / ".yak"
        if (
            (yak / "context.toml").exists()
            or (yak / "state.toml").exists()
            or (yak / "environment.yml").exists()
        ):
            return parent
    return None


def default_artifact_dir() -> Path | None:
    ctx = find_context_root()
    if ctx is None:
        return None
    d = ctx / ".yak" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d
