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
    named_repositories: dict[str, dict] = field(default_factory=dict)

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

    named_repositories: dict[str, dict] = {}
    for name, spec in repos_section.items():
        if name == "sources" or not isinstance(spec, dict):
            continue
        if spec.get("type"):
            named_repositories[name] = spec

    return Context(
        path=root,
        name=ctx_data.get("name", root.name),
        schema=ctx_data.get("schema", "1"),
        source_dirs=source_dirs,
        repository_sources=repository_sources,
        named_repositories=named_repositories,
    )


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
