"""Declared source catalogs — what a source offers (ADR-20).

A source provides a catalog. A catalog answers one question: which
component identities exist here and where is each located. ``bootstrap``
knows catalog locations; the catalog knows component locations; the
resolver knows component identities. Nothing else.
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


class CatalogIdentityError(CatalogError):
    """A catalog declares a component under a name other than its own."""


@dataclass(frozen=True)
class ComponentRef:
    """One component offered by a source: its location relative to the catalog."""

    location: str


@dataclass(frozen=True)
class Catalog:
    """What a single source offers.

    ``spec`` is the source this catalog came from; ``base`` is the
    filesystem root for relative locations of a local source (None for a
    remote source). Locations are source-relative, never absolute.
    """

    spec: str
    base: Path | None
    components: dict[str, ComponentRef] = field(default_factory=dict)


def load_catalog(spec: str, context_root: Path) -> Catalog:
    """Load the catalog of a source spec.

    ``github:owner/repo`` serves ``catalog.yml``; a path suffix
    ``github:owner/repo:path/to/catalog.yml`` selects another catalog in
    the same repository. A local path is read from ``<path>/catalog.yml``.
    The spec is never interpreted beyond selecting the transport and its
    catalog.
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


def fetch_github_artifact(spec: str, location: str) -> Path | None:
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


def _find_artifact_dir(parent: Path) -> Path | None:
    """The subdirectory holding an ``artifact.yml`` (by identity)."""
    if not parent.is_dir():
        return None
    for child in parent.iterdir():
        if child.is_dir() and (child / "artifact.yml").exists():
            return child
    return None


def _parse_catalog(spec: str, base: Path | None, data: dict) -> Catalog:
    components: dict[str, ComponentRef] = {}
    raw_components = data.get("components", {})
    if not isinstance(raw_components, dict):
        raise CatalogError(f"catalog '{spec}': 'components' must be a mapping")
    for name, entry in raw_components.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("location"), str):
            raise CatalogError(f"catalog '{spec}': component '{name}' needs a location")
        components[str(name)] = ComponentRef(location=entry["location"])
    return Catalog(spec=spec, base=base, components=components)


@dataclass(frozen=True)
class Index:
    """The merged, local view of the declared source catalogs.

    ``components`` maps an exact component identity to its catalog and
    reference. First hit wins (source order).
    """

    components: dict[str, tuple[Catalog, ComponentRef]] = field(default_factory=dict)

    def resolve(self, name: str) -> tuple[Catalog, ComponentRef] | None:
        return self.components.get(name)

    def component_names(self) -> list[str]:
        return list(self.components)


def build_index(source_specs: list[str], context_root: Path) -> Index:
    """Merge the declared source catalogs into a flat index.

    Declaration order: a component is taken from the first catalog that
    offers it; later catalogs do not override it. The source list is
    flat — the bootstrap knows catalog locations, nothing nests.
    """
    components: dict[str, tuple[Catalog, ComponentRef]] = {}
    for spec in source_specs:
        catalog = load_catalog(spec, context_root)
        for name, ref in catalog.components.items():
            components.setdefault(name, (catalog, ref))
    return Index(components=components)
