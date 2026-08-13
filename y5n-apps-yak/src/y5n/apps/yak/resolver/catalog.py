"""Declared source catalogs — what a source offers (ADR-20).

A source provides a catalog. A catalog is a recursive list: further
sources, components, and environments. The source graph is walked
depth-first in declaration order into a flat index; resolution is an
exact identity lookup — no searching, no name interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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

    A local path is read from ``<path>/catalog.yml``; a ``github:`` spec
    fetches the catalog from the repository's default branch. The spec is
    never interpreted beyond selecting the transport.
    """
    if spec.startswith("github:"):
        return _load_remote_catalog(spec)
    path = Path(spec)
    if not path.is_absolute():
        path = context_root / path
    return _load_local_catalog(spec, path)


def _load_local_catalog(spec: str, root: Path) -> Catalog:
    catalog_file = root / CATALOG_FILENAME
    if not catalog_file.exists():
        raise CatalogError(f"source '{spec}' has no {CATALOG_FILENAME}")
    try:
        data = yaml.safe_load(catalog_file.read_text()) or {}
    except Exception as exc:
        raise CatalogError(f"cannot read {catalog_file}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{catalog_file} must be a mapping")
    return _parse_catalog(spec, root, data)


def _load_remote_catalog(spec: str) -> Catalog:
    from urllib.request import urlopen

    repo = spec.removeprefix("github:")
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{CATALOG_FILENAME}"
    try:
        with urlopen(url) as resp:
            data = yaml.safe_load(resp.read().decode()) or {}
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{url} must be a mapping")
    return _parse_catalog(spec, None, data)


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
    environments = {
        str(name): str(location) for name, location in raw_environments.items()
    }
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
