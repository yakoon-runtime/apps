"""Declared source catalogs — what a source offers (ADR-20).

A source provides a catalog. A catalog answers one question: which
component identities exist here and where is each located. The source
list knows catalog locations; the catalog knows component locations; the
resolver knows component identities. Nothing else.
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

CATALOG_FILENAME = "catalog.yml"

_BRANCH_CACHE: dict[str, str] = {}


class CatalogError(Exception):
    """A catalog could not be loaded or violated its contract."""


class CatalogIdentityError(CatalogError):
    """A catalog declares a component under a name other than its own."""


@dataclass(frozen=True)
class ComponentRef:
    """One component offered by a source.

    ``location`` is the source-relative path of the component's source;
    ``release`` optionally names the published release the component
    offers (an opaque release identifier, e.g. a tag — the transport
    knows how to turn it into an artifact address).
    """

    location: str
    release: str | None = None


@dataclass(frozen=True)
class Catalog:
    """What a single source offers.

    ``spec`` is the source this catalog came from; ``base`` is the
    filesystem root for relative locations of a local source (None for a
    remote source). Locations are source-relative, never absolute.
    ``bundles`` maps a bundle name to the component names it composes —
    nothing else (a bundle never names other bundles).
    """

    spec: str
    base: Path | None
    components: dict[str, ComponentRef] = field(default_factory=dict)
    bundles: dict[str, tuple[str, ...]] = field(default_factory=dict)


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
    knowledge. The shipped source list is configuration data (the
    packaged default context), never code.
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


def _default_branch(spec: str) -> str:
    """The repository's default branch.

    ``raw.githubusercontent``'s ``HEAD`` alias can serve a stale commit
    shortly after a push; an explicit branch does not. The default branch
    is resolved once per repository through the GitHub API and cached.
    """
    repo = github_repo(spec)
    if repo in _BRANCH_CACHE:
        return _BRANCH_CACHE[repo]
    branch = "main"
    try:
        with urlopen(f"https://api.github.com/repos/{repo}") as resp:
            data = json.loads(resp.read().decode())
        branch = data.get("default_branch") or branch
    except Exception:
        pass
    _BRANCH_CACHE[repo] = branch
    return branch


def _load_remote_catalog(spec: str, catalog_path: str) -> Catalog:
    """Read a remote catalog through the GitHub Contents API.

    The contents API reads the git object directly and is fresh the
    moment a deploy commits; ``raw.githubusercontent``'s CDN can lag
    behind for minutes. The write side already uses the API, so the read
    side follows the same truth.
    """
    repo = github_repo(spec)
    url = f"https://api.github.com/repos/{repo}/contents/{catalog_path}"
    headers = {"Accept": "application/vnd.github.raw+json"}
    token = os.environ.get("YAK_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers)) as resp:
            data = yaml.safe_load(resp.read().decode()) or {}
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{url} must be a mapping")
    return _parse_catalog(spec, None, data)


def fetch_github_release(spec: str, name: str, release: str) -> Path | None:
    """Fetch a component's published release asset from a GitHub source.

    The catalog says *which* release (``release`` is an opaque release
    identifier, e.g. the tag); this adapter knows the asset convention
    (``{name}.artifact.tar.gz``) and the download address shape. There is
    no release scan and no search — the address is fully deterministic.

    The asset is always fetched fresh: a release tag denotes the *current
    build* of that version and ``deploy`` may replace the asset under the
    same tag. A content cache keyed by tag alone would freeze stale
    artifacts, so releases are never cached.
    """
    repo = github_repo(spec)
    url = (
        f"https://github.com/{repo}/releases/download/"
        f"{release}/{name}.artifact.tar.gz"
    )
    with tempfile.TemporaryDirectory() as tmp:
        tarpath = Path(tmp) / f"{name}.artifact.tar.gz"
        try:
            with urlopen(url) as resp:
                tarpath.write_bytes(resp.read())
        except Exception as exc:
            raise CatalogError(f"cannot fetch {url}: {exc}") from exc
        try:
            with tarfile.open(tarpath, "r:gz") as tar:
                tar.extractall(path=tmp, filter="data")
        except Exception as exc:
            raise CatalogError(f"cannot extract {url}: {exc}") from exc
        artifact_dir = _find_artifact_dir(Path(tmp))
        if artifact_dir is None:
            raise CatalogError(f"no artifact for {name} in {url}")
        # The tag denotes the *current build* of that version; deploy may
        # replace the asset under the same tag. Store the fetch under a
        # content-keyed spot (the artifact's own fingerprint), so the
        # caller's path survives this temp dir while a redeployed build
        # never reuses stale content.
        store = _release_store(repo, name, release, artifact_dir)
        return store


def fetch_github_artifact(spec: str, location: str) -> Path | None:
    """Fetch a source-relative location from a GitHub source.

    GitHub is transport only: the index already decided the location. A
    location is a path inside the repository (the component's folder);
    it is fetched from the repo archive and extracted — no release scan,
    no search.
    """
    if location.startswith("releases/") or location.startswith("/"):
        raise CatalogError(
            f"github source '{spec}': location must be a path inside the "
            f"repository, got '{location}'"
        )
    repo = github_repo(spec)
    url = f"https://codeload.github.com/{repo}/tar.gz/{_default_branch(spec)}"

    cache_root = (
        Path.home() / ".yak" / "cache" / "github" / repo / location.replace("/", "_")
    )
    artifact_dir = _find_artifact_dir(cache_root)
    if artifact_dir is not None:
        return artifact_dir

    with tempfile.TemporaryDirectory() as tmp:
        tarpath = Path(tmp) / "repo.tar.gz"
        try:
            with urlopen(url) as resp:
                tarpath.write_bytes(resp.read())
        except Exception as exc:
            raise CatalogError(f"cannot fetch {url}: {exc}") from exc
        try:
            with tarfile.open(tarpath, "r:gz") as tar:
                tar.extractall(path=tmp, filter="data")
        except Exception as exc:
            raise CatalogError(f"cannot extract {url}: {exc}") from exc
        found = _find_location_dir(Path(tmp), location)
        if found is None:
            raise CatalogError(f"no {location} in {url}")
        cache_root.mkdir(parents=True, exist_ok=True)
        cached = cache_root / found.name
        if not cached.exists():
            shutil.copytree(found, cached)
        return cached


def _find_location_dir(parent: Path, location: str) -> Path | None:
    """The repo-relative ``location`` inside an extracted repo archive.

    codeload wraps the tree in a single top-level directory; the
    location is resolved relative to that root.
    """
    roots = [d for d in parent.iterdir() if d.is_dir()]
    if len(roots) != 1:
        return None
    candidate = roots[0] / location
    return candidate if candidate.is_dir() else None


def _find_artifact_dir(parent: Path) -> Path | None:
    """The subdirectory holding an ``artifact.yml`` (by identity)."""
    if not parent.is_dir():
        return None
    for child in parent.iterdir():
        if child.is_dir() and (child / "artifact.yml").exists():
            return child
    return None


def _release_store(repo: str, name: str, release: str, artifact_dir: Path) -> Path:
    """Persist a fetched release artifact under its content identity.

    The store key combines the release with the artifact's own
    fingerprint, so the same tag re-deployed with a different build lands
    in a different spot and stale content is never reused.
    """
    import y5n.apps.yak.resolver.artifact as artifact_mod

    fingerprint = ""
    manifest = artifact_dir / "artifact.yml"
    if manifest.exists():
        meta = artifact_mod._parse_manifest(manifest)
        fp = meta.get("fingerprint", "")
        if fp.startswith("sha256:"):
            fp = fp[7:]
        fingerprint = fp[:12]
    key = f"{name}-{release}-{fingerprint}" if fingerprint else f"{name}-{release}"
    store = Path.home() / ".yak" / "cache" / "github" / repo / key / name
    if not store.exists():
        store.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(artifact_dir, store)
    return store


def _parse_catalog(spec: str, base: Path | None, data: dict) -> Catalog:
    components: dict[str, ComponentRef] = {}
    raw_components = data.get("components", {})
    if not isinstance(raw_components, dict):
        raise CatalogError(f"catalog '{spec}': 'components' must be a mapping")
    for name, entry in raw_components.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("location"), str):
            raise CatalogError(f"catalog '{spec}': component '{name}' needs a location")
        release = entry.get("release")
        if release is not None and not isinstance(release, str):
            raise CatalogError(
                f"catalog '{spec}': component '{name}' release must be a string"
            )
        components[str(name)] = ComponentRef(
            location=entry["location"], release=release
        )
    bundles = _parse_bundles(spec, data)
    return Catalog(spec=spec, base=base, components=components, bundles=bundles)


def _parse_bundles(spec: str, data: dict) -> dict[str, tuple[str, ...]]:
    """Parse a catalog's ``bundles:`` — name → list of component names.

    A bundle names components only; it never names another bundle in this
    version. Names are opaque identities — whether they resolve through
    the shared index is an install-time concern, not a parse error here.
    """
    raw_bundles = data.get("bundles", {})
    if not raw_bundles:
        return {}
    if not isinstance(raw_bundles, dict):
        raise CatalogError(f"catalog '{spec}': 'bundles' must be a mapping")
    bundles: dict[str, tuple[str, ...]] = {}
    for name, members in raw_bundles.items():
        if not isinstance(members, list) or not all(
            isinstance(m, str) for m in members
        ):
            raise CatalogError(
                f"catalog '{spec}': bundle '{name}' must be a list of "
                "component names"
            )
        bundles[str(name)] = tuple(members)
    return bundles


@dataclass(frozen=True)
class Index:
    """The merged, local view of the declared source catalogs.

    ``components`` maps an exact component identity to its catalog and
    reference; ``bundles`` maps a bundle name to its catalog and member
    list. First hit wins (source order) in both namespaces.
    """

    components: dict[str, tuple[Catalog, ComponentRef]] = field(default_factory=dict)
    bundles: dict[str, tuple[Catalog, tuple[str, ...]]] = field(default_factory=dict)

    def resolve(self, name: str) -> tuple[Catalog, ComponentRef] | None:
        return self.components.get(name)

    def resolve_bundle(self, name: str) -> tuple[Catalog, tuple[str, ...]] | None:
        return self.bundles.get(name)


def build_index(source_specs: list[str], context_root: Path) -> Index:
    """Merge the declared source catalogs into a flat index.

    Declaration order: a component or bundle is taken from the first
    catalog that offers it; later catalogs do not override it. The source
    list is flat — it knows catalog locations, nothing nests.
    """
    components: dict[str, tuple[Catalog, ComponentRef]] = {}
    bundles: dict[str, tuple[Catalog, tuple[str, ...]]] = {}
    for spec in source_specs:
        catalog = load_catalog(spec, context_root)
        for name, ref in catalog.components.items():
            components.setdefault(name, (catalog, ref))
        for name, members in catalog.bundles.items():
            bundles.setdefault(name, (catalog, members))
    return Index(components=components, bundles=bundles)
