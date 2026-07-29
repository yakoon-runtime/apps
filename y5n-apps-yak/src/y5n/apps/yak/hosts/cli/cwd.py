from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Context:
    """A YakContext — describes a development environment.

    Loaded from .yak/context.toml. Provides two independent concerns:
    - Sources: where source code is developed (build, create)
    - Repositories: where published artifacts are consumed (install, sync)
    """

    path: Path
    name: str = ""
    schema: str = "1"
    source_dirs: list[Path] = field(default_factory=list)
    repository_sources: list[str] = field(default_factory=list)

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
    sources_section = data.get("sources", {})
    raw_dirs = sources_section.get("dirs", [])
    source_dirs = [Path(r) for r in raw_dirs] if isinstance(raw_dirs, list) else []

    repos_section = data.get("repositories", {})
    raw_repos = repos_section.get("sources", [])
    repository_sources = list(raw_repos) if isinstance(raw_repos, list) else []

    return Context(
        path=root,
        name=ctx_data.get("name", root.name),
        schema=ctx_data.get("schema", "1"),
        source_dirs=source_dirs,
        repository_sources=repository_sources,
    )


def default_sources() -> list[Path]:
    """Fallback: monorepo paths relative to this source file."""
    root = Path(__file__).resolve().parents[8]
    return [root / d for d in ("packs", "runtime", "apps", "sdk", root)]


def find_context_root() -> Path | None:
    cwd = Path.cwd()
    found: Path | None = None
    for parent in [cwd, *cwd.parents]:
        if (parent / ".yak" / "context.toml").exists():
            found = parent
    return found


def default_artifact_dir() -> Path | None:
    ctx = find_context_root()
    if ctx is None:
        return None
    d = ctx / ".yak" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d
