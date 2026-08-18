"""Declared source catalogs — what a source offers (ADR-20).

A source provides a catalog. A catalog answers two questions: which
components exist here and where each is located. Since ADR-23 Step 3 the
catalog never declares an identity — it lists locations, and each
location's component declares itself in ``.yak/component.yml``. The
source list knows catalog locations; the catalog knows component
locations; the resolver knows component identities. Nothing else.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import Request, urlopen

import yaml
from packaging.version import InvalidVersion, Version

from y5n.apps.yak.cap.models import cap_from_data, read_component

CATALOG_FILENAME = "catalog.yml"

_BRANCH_CACHE: dict[str, str] = {}


class CatalogError(Exception):
    """A catalog could not be loaded or violated its contract."""


@dataclass(frozen=True)
class ComponentRef:
    """One component offered by a source.

    ``location`` is the source-relative path of the component's source.
    The catalog describes *where* a component is — it never carries an
    identity or a version (ADR-23 Step 3): the component declares itself
    in ``.yak/component.yml``. Published releases are discovered from the
    repository itself (see ``_repo_release_index``).
    """

    location: str


@dataclass(frozen=True)
class Catalog:
    """What a single source offers.

    ``spec`` is the source this catalog came from; ``base`` is the
    filesystem root for relative locations of a local source (None for a
    remote source). Locations are source-relative, never absolute.
    ``components`` lists the locations, in declaration order; ``bundles``
    maps a bundle name to the component names it composes — nothing else
    (a bundle never names other bundles).
    """

    spec: str
    base: Path | None
    components: list[ComponentRef] = field(default_factory=list)
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
    side follows the same truth. Reads are cached briefly so a repeated
    command does not re-fetch every source's catalog.
    """
    repo = github_repo(spec)
    cached = _cached_remote_catalog(spec, repo, catalog_path)
    if cached is not None:
        return cached
    url = f"https://api.github.com/repos/{repo}/contents/{catalog_path}"
    headers = {"Accept": "application/vnd.github.raw+json"}
    try:
        with urlopen(Request(url, headers=headers)) as resp:
            data = yaml.safe_load(resp.read().decode()) or {}
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{url} must be a mapping")
    _store_remote_catalog(spec, repo, catalog_path, data)
    return _parse_catalog(spec, None, data)


# How long a fetched remote catalog may be reused before re-fetching.
CATALOG_TTL_SECONDS = 60.0


def _catalog_cache_path(repo: str, catalog_path: str) -> Path:
    return (
        Path.home()
        / ".yak"
        / "cache"
        / "catalogs"
        / repo.replace("/", "_")
        / catalog_path
    )


def _cached_remote_catalog(spec: str, repo: str, catalog_path: str) -> Catalog | None:
    path = _catalog_cache_path(repo, catalog_path)
    if not path.exists() or time.time() - path.stat().st_mtime > CATALOG_TTL_SECONDS:
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return _parse_catalog(spec, None, data)


def _store_remote_catalog(
    spec: str, repo: str, catalog_path: str, data: dict
) -> None:
    try:
        path = _catalog_cache_path(repo, catalog_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
    except Exception:
        pass


def fetch_github_release(spec: str, name: str) -> Path | None:
    """Fetch a component's published release asset from a GitHub source.

    The released version is discovered from the repository's own release
    list — the catalog carries no version. ``deploy`` and this reader
    share the convention: a release tag is ``{name}-v{version}`` and its
    asset is ``{name}.artifact.tar.gz``; the reader picks the highest
    published version. The remote asset is validated by its GitHub asset
    digest (the sha256 of the published tarball) before it is
    (re)downloaded. When the digest is unchanged and the local content is
    present, the download is skipped entirely. The digest is a transport
    identity — distinct from the artifact's own fingerprint (the build
    identity), which is read from the artifact afterwards.
    """
    repo = github_repo(spec)
    entry = _repo_release_index(repo).get(name)
    if entry is None:
        raise CatalogError(
            f"component '{name}' has no release — use a --path catalog instead"
        )
    tag, digest = entry

    cache_root = (
        Path.home() / ".yak" / "cache" / "github" / repo / f"{name}-{tag}"
    )
    if digest is not None:
        stored = _cached_release(cache_root, digest)
        if stored is not None:
            return stored

    url = (
        f"https://github.com/{repo}/releases/download/"
        f"{tag}/{name}.artifact.tar.gz"
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
        return _store_release(cache_root, artifact_dir, digest)


_ASSET_SUFFIX = ".artifact.tar.gz"

# Repo → (fetched at, {component: (tag, asset digest)}). The index is a
# transport view of the repository, never a version truth.
_RELEASE_INDEX_CACHE: dict[str, tuple[float, dict[str, tuple[str, str | None]]]] = {}
_RELEASE_INDEX_LOCK = threading.Lock()
_RELEASE_INDEX_TTL_SECONDS = 60.0


def _repo_release_index(repo: str) -> dict[str, tuple[str, str | None]]:
    """Component → (tag, digest) of its highest published release, per repo.

    Loaded once per repository — never per component — and cached briefly.
    Thread-safe: concurrent resolution of several components of the same
    repository triggers a single scan.
    """
    now = time.time()
    cached = _RELEASE_INDEX_CACHE.get(repo)
    if cached is not None and now - cached[0] < _RELEASE_INDEX_TTL_SECONDS:
        return cached[1]
    with _RELEASE_INDEX_LOCK:
        cached = _RELEASE_INDEX_CACHE.get(repo)
        if cached is not None and now - cached[0] < _RELEASE_INDEX_TTL_SECONDS:
            return cached[1]
        index = _index_repo_releases(_fetch_releases(repo))
        _RELEASE_INDEX_CACHE[repo] = (time.time(), index)
        return index


def _fetch_releases(repo: str) -> list[dict]:
    """All releases of a repository (paginated, best-effort).

    Reads are anonymous: a public ``github:`` source needs no credential,
    and an accidentally set token must not change read semantics.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    releases: list[dict] = []
    page = 1
    while True:
        url = (
            "https://api.github.com/repos/"
            f"{repo}/releases?per_page=100&page={page}"
        )
        try:
            with urlopen(Request(url, headers=headers)) as resp:
                batch = json.loads(resp.read().decode())
        except Exception:
            break
        if not isinstance(batch, list) or not batch:
            break
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return releases


def _index_repo_releases(releases: list[dict]) -> dict[str, tuple[str, str | None]]:
    """Component → (tag, digest) of the highest release with a valid asset.

    Pure selection, shared by the transport and the tests: a release
    counts when its tag is ``{name}-v{version}`` and it carries the
    ``{name}.artifact.tar.gz`` asset. The highest version wins — compared
    as versions, never lexically (``0.10.0`` beats ``0.9.0``). Tags with a
    different prefix or a different asset are irrelevant noise (legacy
    releases in shared repositories included).
    """
    best: dict[str, tuple[str, str | None]] = {}
    best_version: dict[str, Version] = {}
    for release in releases:
        tag = release.get("tag_name", "")
        for asset in release.get("assets", []):
            asset_name = asset.get("name", "")
            if not asset_name.endswith(_ASSET_SUFFIX):
                continue
            name = asset_name[: -len(_ASSET_SUFFIX)]
            prefix = f"{name}-v"
            if not tag.startswith(prefix):
                continue
            version = tag[len(prefix) :]
            key = _version_key(version)
            if name not in best_version or key > best_version[name]:
                best[name] = (tag, asset.get("digest"))
                best_version[name] = key
    return best


def _version_key(version: str) -> Version:
    """A comparable version key; an unparseable version sorts lowest."""
    try:
        return Version(version)
    except InvalidVersion:
        return Version("0")


def _cached_release(cache_root: Path, digest: str) -> Path | None:
    """The locally stored artifact whose recorded digest matches the remote.

    The digest guards the mutable release: the cache is only reused when
    the published asset is unchanged, so a tag alone is never a cache key.
    """
    manifest = cache_root / "manifest.json"
    if not manifest.exists():
        return None
    try:
        meta = json.loads(manifest.read_text())
    except Exception:
        return None
    if meta.get("digest") != digest:
        return None
    artifact_dir = _find_artifact_dir(cache_root / "artifact")
    if artifact_dir is None:
        return None
    return artifact_dir


def _store_release(cache_root: Path, artifact_dir: Path, digest: str | None) -> Path:
    """Persist a fetched release under its manifest-guarded cache spot."""
    store = cache_root / "artifact"
    if store.exists():
        shutil.rmtree(store, ignore_errors=True)
    store.mkdir(parents=True, exist_ok=True)
    shutil.copytree(artifact_dir, store / artifact_dir.name)
    meta = {"digest": digest} if digest else {}
    (cache_root / "manifest.json").write_text(json.dumps(meta))
    return store / artifact_dir.name


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


def _parse_catalog(spec: str, base: Path | None, data: dict) -> Catalog:
    components: list[ComponentRef] = []
    raw_components = data.get("components") or []
    if not isinstance(raw_components, list):
        raise CatalogError(
            f"catalog '{spec}': 'components' must be a list of locations"
        )
    for entry in raw_components:
        if not isinstance(entry, dict) or not isinstance(
            entry.get("location"), str
        ):
            raise CatalogError(
                f"catalog '{spec}': each component needs a 'location'"
            )
        # Only ``location`` is read. The catalog never declares identity
        # (component.yml owns it) or distribution (the source owns it) —
        # any other field is ignored for forward compatibility.
        components.append(ComponentRef(location=entry["location"]))
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

    ``components`` maps an exact component identity (declared in each
    location's component.yml) to its catalog and reference; ``bundles``
    maps a bundle name to its catalog and member list. First hit wins
    (source order) in both namespaces.
    """

    components: dict[str, tuple[Catalog, ComponentRef]] = field(default_factory=dict)
    bundles: dict[str, tuple[Catalog, tuple[str, ...]]] = field(default_factory=dict)

    def resolve(self, name: str) -> tuple[Catalog, ComponentRef] | None:
        return self.components.get(name)

    def resolve_bundle(self, name: str) -> tuple[Catalog, tuple[str, ...]] | None:
        return self.bundles.get(name)


def build_index(source_specs: list[str], context_root: Path) -> Index:
    """Merge the declared source catalogs into a flat index.

    A catalog lists locations (ADR-23 Step 3); the merged index resolves
    each location's identity from its ``.yak/component.yml`` — locally
    from disk, remotely through one small Contents-API request per
    location. The catalog never declares identity, so no catalog/component
    identity conflict can exist. Declaration order: a component or bundle
    is taken from the first catalog that offers it; later catalogs do not
    override it. The source list is flat — it knows catalog locations,
    nothing nests.
    """
    components: dict[str, tuple[Catalog, ComponentRef]] = {}
    bundles: dict[str, tuple[Catalog, tuple[str, ...]]] = {}
    for spec in source_specs:
        catalog = load_catalog(spec, context_root)
        for ref in catalog.components:
            name = discover_component_identity(catalog, ref.location)
            components.setdefault(name, (catalog, ref))
        for name, members in catalog.bundles.items():
            bundles.setdefault(name, (catalog, members))
    return Index(components=components, bundles=bundles)


def discover_component_identity(catalog: Catalog, location: str) -> str:
    """The component identity a catalog location offers.

    The identity is read from the component's own ``.yak/component.yml``
    (ADR-23) — locally from disk, remotely through the Contents API. A
    location that does not declare an identity violates the catalog
    contract (``components`` lists component roots, nothing else).
    """
    if catalog.base is not None:
        cap = read_component(catalog.base / location)
        if cap is None:
            raise CatalogError(
                f"catalog '{catalog.spec}': component at '{location}' has "
                "no .yak/component.yml"
            )
        return cap.name
    return _fetch_component_yml(catalog.spec, location)


def _component_cache_path(repo: str, location: str) -> Path:
    return (
        Path.home()
        / ".yak"
        / "cache"
        / "catalogs"
        / repo.replace("/", "_")
        / location.replace("/", "_")
        / "component.yml"
    )


def _fetch_component_yml(spec: str, location: str) -> str:
    """The identity declared by a remote catalog location (component.yml).

    Remote discovery reads only the component's own manifest through the
    GitHub Contents API — one small request per location, never a repo
    tarball. Reads are cached briefly like remote catalogs.
    """
    repo = github_repo(spec)
    path = _component_cache_path(repo, location)
    if path.exists() and time.time() - path.stat().st_mtime <= CATALOG_TTL_SECONDS:
        try:
            cap = cap_from_data(yaml.safe_load(path.read_text()) or {})
            if cap is not None:
                return cap.name
        except Exception:
            pass
    url = (
        f"https://api.github.com/repos/{repo}/contents/"
        f"{location}/.yak/component.yml"
    )
    headers = {"Accept": "application/vnd.github.raw+json"}
    try:
        with urlopen(Request(url, headers=headers)) as resp:
            text = resp.read().decode()
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    cap = cap_from_data(yaml.safe_load(text) or {})
    if cap is None:
        raise CatalogError(
            f"component at '{location}' in {spec} has no .yak/component.yml"
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    except Exception:
        pass
    return cap.name
