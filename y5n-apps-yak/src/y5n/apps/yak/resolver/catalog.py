"""Declared source catalogs — what a source offers (ADR-20).

A source provides a catalog. A catalog is a recursive list: further
sources, components, and environments. The source graph is walked
depth-first in declaration order into a flat index; resolution is an
exact identity lookup — no searching, no name interpretation.
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlopen

import yaml

CATALOG_FILENAME = "catalog.yml"


class CatalogError(Exception):
    """A catalog could not be loaded or violated its contract."""


class CatalogCycleError(CatalogError):
    """The source graph contains a cycle."""


class CatalogIdentityError(CatalogError):
    """A catalog declares a component under a name other than its own."""


@dataclass(frozen=True)
class ComponentRef:
    """One component offered by a source: version + source-relative location."""

    version: str
    location: str
    fingerprint: str = ""


@dataclass(frozen=True)
class Catalog:
    """What a single source offers.

    ``spec`` is the source this catalog came from; ``base`` is the
    filesystem root for relative locations of a local source (None for a
    remote source). Locations are source-relative, never absolute.
    """

    spec: str
    base: Path | None
    sub_sources: tuple[str, ...] = ()
    components: dict[str, ComponentRef] = field(default_factory=dict)
    environments: dict[str, str] = field(default_factory=dict)


def load_catalog(spec: str, context_root: Path) -> Catalog:
    """Load the catalog of a source spec.

    ``github:owner/repo`` serves ``catalog.yml``; a path suffix
    ``github:owner/repo:path/to/catalog.yml`` selects another catalog in
    the same repository. ``yakoon:official`` is the bootstrap pointer to
    the official source list. A local path is read from
    ``<path>/catalog.yml``. The spec is never interpreted beyond selecting
    the transport and its catalog.
    """
    kind, _repo, catalog_path = _split_spec(spec)
    if kind == "github":
        return _load_remote_catalog(spec, catalog_path)
    path = Path(_repo)
    if not path.is_absolute():
        path = context_root / path
    return _load_local_catalog(spec, path, catalog_path)


def _split_spec(spec: str) -> tuple[str, str, str]:
    """(kind, location, catalog-path) of a source spec.

    - ``github:owner/repo[:path/to/catalog.yml]``
    - a local path

    The spec is always an explicit location — no aliases, no product
    knowledge. A bootstrap pointer is configuration data (the packaged
    default context), never code.
    """
    if spec.startswith("github:"):
        rest = spec.removeprefix("github:")
        if ":" in rest:
            repo, catalog_path = rest.split(":", 1)
            return "github", f"github:{repo}", catalog_path
        return "github", spec, CATALOG_FILENAME
    return "local", spec, CATALOG_FILENAME


def github_repo(spec: str) -> str:
    """The repository part of a github source spec (ignoring the path)."""
    return _split_spec(spec)[1].removeprefix("github:")


def _load_local_catalog(spec: str, root: Path, catalog_path: str) -> Catalog:
    catalog_file = root / catalog_path
    if not catalog_file.exists():
        raise CatalogError(f"source '{spec}' has no {catalog_path}")
    try:
        data = yaml.safe_load(catalog_file.read_text()) or {}
    except Exception as exc:
        raise CatalogError(f"cannot read {catalog_file}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{catalog_file} must be a mapping")
    return _parse_catalog(spec, root, data)


def _load_remote_catalog(spec: str, catalog_path: str) -> Catalog:
    repo = github_repo(spec)
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{catalog_path}"
    try:
        with urlopen(url) as resp:
            data = yaml.safe_load(resp.read().decode()) or {}
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{url} must be a mapping")
    return _parse_catalog(spec, None, data)


def fetch_github_artifact(
    spec: str, location: str, fingerprint: str = ""
) -> Path | None:
    """Fetch a source-relative location from a GitHub source.

    GitHub is transport only: the index already decided the location. A
    github location is ``<tag>/<asset>`` and maps directly to the public
    download endpoint — no release scan, no search.
    """
    if location.startswith("releases/") or location.startswith("/"):
        raise CatalogError(
            f"github source '{spec}': location must be '<tag>/<asset>', "
            f"got '{location}'"
        )
    repo = github_repo(spec)
    url = f"https://github.com/{repo}/releases/download/{location}"

    cache_root = (
        Path.home() / ".yak" / "cache" / "github" / repo / location.replace("/", "_")
    )
    artifact_dir = _find_artifact_dir(cache_root)
    if artifact_dir is not None:
        return artifact_dir

    try:
        with urlopen(url) as resp:
            data = resp.read()
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc

    with tempfile.TemporaryDirectory() as tmp:
        tarpath = Path(tmp) / "resource.tar.gz"
        tarpath.write_bytes(data)
        try:
            with tarfile.open(tarpath, "r:gz") as tar:
                tar.extractall(path=tmp, filter="data")
        except Exception as exc:
            raise CatalogError(f"cannot extract {url}: {exc}") from exc
        found = _find_artifact_dir(Path(tmp))
        if found is None:
            raise CatalogError(f"no artifact in {url}")
        cache_root.mkdir(parents=True, exist_ok=True)
        cached = cache_root / found.name
        if not cached.exists():
            shutil.copytree(found, cached)
        return cached


def fetch_github_file(spec: str, location: str) -> Path:
    """Fetch a git-tree resource (e.g. an environment manifest) from a source.

    Environments are plain files in the repository's default branch, not
    release assets; the location is the file path within the repo.
    """
    repo = github_repo(spec)
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{location}"
    try:
        with urlopen(url) as resp:
            data = resp.read()
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    path = Path(tempfile.mkdtemp()) / Path(location).name
    path.write_bytes(data)
    return path


def _find_artifact_dir(parent: Path) -> Path | None:
    """The subdirectory holding an ``artifact.yml`` (by identity)."""
    if not parent.is_dir():
        return None
    for child in parent.iterdir():
        if child.is_dir() and (child / "artifact.yml").exists():
            return child
    return None


def _parse_catalog(spec: str, base: Path | None, data: dict) -> Catalog:
    raw_sources = data.get("sources", [])
    if not isinstance(raw_sources, list):
        raise CatalogError(f"catalog '{spec}': 'sources' must be a list")
    components: dict[str, ComponentRef] = {}
    raw_components = data.get("components", {})
    if not isinstance(raw_components, dict):
        raise CatalogError(f"catalog '{spec}': 'components' must be a mapping")
    for name, entry in raw_components.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("location"), str):
            raise CatalogError(f"catalog '{spec}': component '{name}' needs a location")
        components[str(name)] = ComponentRef(
            version=str(entry.get("version", "")),
            location=entry["location"],
            fingerprint=str(entry.get("fingerprint", "")),
        )
    raw_environments = data.get("environments", {})
    if not isinstance(raw_environments, dict):
        raise CatalogError(f"catalog '{spec}': 'environments' must be a mapping")
    environments: dict[str, str] = {}
    for name, value in raw_environments.items():
        location = value.get("location") if isinstance(value, dict) else value
        if not isinstance(location, str) or not location:
            raise CatalogError(
                f"catalog '{spec}': environment '{name}' needs a location"
            )
        environments[str(name)] = location
    return Catalog(
        spec=spec,
        base=base,
        sub_sources=tuple(str(s) for s in raw_sources),
        components=components,
        environments=environments,
    )


@dataclass(frozen=True)
class Index:
    """The merged, local view of the walked source graph.

    ``components`` maps an exact component identity to its catalog and
    reference; ``environments`` maps an environment name to its catalog
    and location. First hit wins (source order, depth-first).
    """

    components: dict[str, tuple[Catalog, ComponentRef]] = field(default_factory=dict)
    environments: dict[str, tuple[Catalog, str]] = field(default_factory=dict)

    def resolve(self, name: str) -> tuple[Catalog, ComponentRef] | None:
        return self.components.get(name)

    def resolve_environment(self, name: str) -> tuple[Catalog, str] | None:
        return self.environments.get(name)

    def component_names(self) -> list[str]:
        return list(self.components)


def build_index(source_specs: list[str], context_root: Path) -> Index:
    """Walk the source graph into a flat index.

    Depth-first, declaration order: a source's own resources, then its
    sub-sources recursively, then the next declared source. A cycle is a
    load error; an already-visited source is not walked twice.
    """
    components: dict[str, tuple[Catalog, ComponentRef]] = {}
    environments: dict[str, tuple[Catalog, str]] = {}
    visited: set[str] = set()

    def walk(spec: str, stack: tuple[str, ...]) -> None:
        if spec in stack:
            raise CatalogCycleError(f"source cycle: {' -> '.join((*stack, spec))}")
        if spec in visited:
            return
        visited.add(spec)
        catalog = load_catalog(spec, context_root)
        for name, ref in catalog.components.items():
            components.setdefault(name, (catalog, ref))
        for name, location in catalog.environments.items():
            environments.setdefault(name, (catalog, location))
        for sub in catalog.sub_sources:
            walk(sub, (*stack, spec))

    for spec in source_specs:
        walk(spec, ())
    return Index(components=components, environments=environments)
