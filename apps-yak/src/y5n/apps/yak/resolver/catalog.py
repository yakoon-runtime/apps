"""Declared source catalogs — what a source offers (ADR-20, ADR-23 Step 4).

A source provides a catalog. A catalog answers two questions: which
components exist here and where each is located. Since ADR-23 Step 4 the
catalog is a ``name → location`` mapping: the catalog key is a discovery
binding / index key only — never a normative identity. Identity and
version live in each component's ``.yak/component.yml``; the published
builds of each component resolve through the component's own
``.yak/releases.yml`` next to it (same transport as the catalog). The
source list knows catalog locations; the catalog knows component names and
locations; each component's release catalog owns the builds that component
has published. Nothing else.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

CATALOG_FILENAME = "catalog.yml"
RELEASES_FILENAME = "releases.yml"

# Diagnostics: when set to a list, every outbound URL (API + download) is
# appended before the request is made. Used by the E2E harness to count
# discovery/release-resolution requests; None in normal operation (no cost).
URL_TRACE: list[str] | None = None


def _trace(url: str) -> None:
    """Record an outbound URL for diagnostics/request counting.

    Appends to the in-process list (URL_TRACE) and to the optional trace
    file named by ``YAK_TRACE_FILE`` (the CLI runs in a subprocess, so the
    file is what the E2E harness reads back). None disabled in normal use.
    """
    if URL_TRACE is not None:
        URL_TRACE.append(url)
    trace_file = os.environ.get("YAK_TRACE_FILE")
    if trace_file:
        with open(trace_file, "a") as fh:
            fh.write(url + "\n")


_BRANCH_CACHE: dict[str, str] = {}


class CatalogError(Exception):
    """A catalog could not be loaded or violated its contract."""


@dataclass(frozen=True)
class ComponentRef:
    """One component offered by a source.

    ``name`` is the discovery binding / index key the catalog declares
    (ADR-23 Step 4) — it is *not* a normative identity. ``location`` is
    the source-relative path of the component's source. Identity and
    version live in ``.yak/component.yml``; the published builds resolve
    through the component's own ``.yak/releases.yml``. The catalog never
    declares a version, a release, a digest or a distribution.
    """

    name: str
    location: str


@dataclass(frozen=True)
class Catalog:
    """What a single source offers.

    ``spec`` is the source this catalog came from; ``base`` is the
    filesystem root for relative locations of a local source (None for a
    remote source). Locations are source-relative, never absolute.
    ``components`` lists the name → location bindings, in declaration
    order; ``bundles`` maps a bundle name to the component names it
    composes — nothing else (a bundle never names other bundles).
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
    _trace(f"https://api.github.com/repos/{repo}")
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
    _trace(url)
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


def _store_remote_catalog(spec: str, repo: str, catalog_path: str, data: dict) -> None:
    try:
        path = _catalog_cache_path(repo, catalog_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
    except Exception:
        pass


def fetch_github_release(spec: str, name: str, location: str) -> Path | None:
    """Fetch a component's currently offered artifact from a GitHub source.

    The offered release is the component's own ``.yak/releases.yml`` at its
    catalog ``location`` (ADR-23 Step 4) — the catalog carries no version
    and the GitHub Releases API is never scanned. The currently offered
    build is the catalog's highest released version. The download goes
    through the release asset CDN; the recorded digest (written by
    ``deploy`` at publish time) is checked against the downloaded bytes
    before the artifact is used or reused. When the digest is unchanged and
    the local content is present, the download is skipped entirely. The
    digest is a transport identity — distinct from the artifact's own
    fingerprint (the build identity), which is read from the artifact
    afterwards.
    """
    releases = _fetch_releases(spec, location)
    selected = _select_offered(releases)
    if selected is None:
        raise CatalogError(
            f"component '{name}' is not offered by {spec} (no releases.yml "
            "entry) — use a --path catalog instead"
        )
    tag = selected.tag
    digest = selected.digest

    repo = github_repo(spec)
    cache_root = Path.home() / ".yak" / "cache" / "github" / repo / f"{name}-{tag}"
    if digest is not None:
        stored = _cached_release(cache_root, digest)
        if stored is not None:
            return stored

    url = (
        f"https://github.com/{repo}/releases/download/" f"{tag}/{name}.artifact.tar.gz"
    )
    with tempfile.TemporaryDirectory() as tmp:
        tarpath = Path(tmp) / f"{name}.artifact.tar.gz"
        _trace(url)
        try:
            with urlopen(url) as resp:
                tarpath.write_bytes(resp.read())
        except Exception as exc:
            raise CatalogError(f"cannot fetch {url}: {exc}") from exc
        if digest is not None:
            actual = _sha256_hex(tarpath.read_bytes())
            if actual != digest:
                raise CatalogError(
                    f"digest mismatch for {name}: release.yml records "
                    f"{digest}, downloaded {actual} — the published asset "
                    "changed after deploy"
                )
        try:
            with tarfile.open(tarpath, "r:gz") as tar:
                tar.extractall(path=tmp, filter="data")
        except Exception as exc:
            raise CatalogError(f"cannot extract {url}: {exc}") from exc
        artifact_dir = _find_artifact_dir(Path(tmp))
        if artifact_dir is None:
            raise CatalogError(f"no artifact for {name} in {url}")
        return _store_release(cache_root, artifact_dir, digest)


def _sha256_hex(data: bytes) -> str:
    """The artifact digest format shared with deploy: ``sha256:<hex>``."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ReleaseRef:
    """One published build of a component (``.yak/releases.yml``).

    The release catalog of a component is keyed by ``version`` — the
    version is the identifier of a published build, not a second authority
    (the component owns its version in ``.yak/component.yml``). ``tag``
    selects the release asset (``{name}.artifact.tar.gz`` at
    ``releases/download/{tag}/``); ``digest`` is the sha256 of the
    published tarball and identifies the concrete build.
    """

    version: str
    tag: str
    digest: str | None


def release_index_path(location: str) -> str:
    """The ``releases.yml`` path where a component keeps its releases.

    The release catalog belongs to the component, not the repository: it
    lives beside the component's own ``.yak/component.yml`` at its catalog
    ``location`` (``{location}/.yak/releases.yml``, ADR-23 Step 4). A
    component grouped by a repo root uses ``.yak/releases.yml``.
    """
    loc = location.lstrip("./")
    return f"{loc}/.yak/{RELEASES_FILENAME}" if loc else f".yak/{RELEASES_FILENAME}"


def _version_key(version: str) -> tuple:
    """A comparable version key: ``0.9.0 < 0.10.0``, never lexical."""
    parts = []
    for segment in version.replace("-", ".").split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _select_offered(releases: dict[str, ReleaseRef]) -> ReleaseRef | None:
    """The currently offered build: the highest released version.

    ``install`` resolves the highest version of the component's release
    catalog today; a version pin (``runtime-engine@0.7.0``) or constraint
    (``>=0.7,<0.9``) is a later resolver concern that reads the same
    catalog.
    """
    if not releases:
        return None
    return max(releases.values(), key=lambda ref: _version_key(ref.version))


def _parse_releases(spec: str, data: dict) -> dict[str, ReleaseRef]:
    """Parse a component's release catalog (``.yak/releases.yml``).

    Contract (ADR-23 Step 4): ``releases: {version: {tag, digest}}``. The
    version is the identifier of a published build — the component owns it
    in ``component.yml``, deploy only registers that a concrete artifact
    exists for it. No name, no dependencies: the catalog owns published
    builds only.
    """
    raw = data.get("releases") or {}
    if not isinstance(raw, dict):
        raise CatalogError(f"release catalog '{spec}': 'releases' must be a mapping")
    releases: dict[str, ReleaseRef] = {}
    for version, entry in raw.items():
        if not isinstance(version, str) or not version:
            raise CatalogError(
                f"release catalog '{spec}': release keys must be non-empty versions"
            )
        if not isinstance(entry, dict):
            raise CatalogError(
                f"release catalog '{spec}': release '{version}' must be a "
                "mapping with tag and digest"
            )
        tag = entry.get("tag")
        if not isinstance(tag, str) or not tag:
            raise CatalogError(
                f"release catalog '{spec}': release '{version}' needs a 'tag'"
            )
        digest = entry.get("digest")
        if digest is not None and not isinstance(digest, str):
            raise CatalogError(
                f"release catalog '{spec}': release '{version}' digest must "
                "be a string"
            )
        releases[version] = ReleaseRef(version=version, tag=tag, digest=digest)
    return releases


def _release_cache_path(repo: str, release_path: str) -> Path:
    return _catalog_cache_path(repo, release_path)


def _cached_releases(
    spec: str, repo: str, release_path: str
) -> dict[str, ReleaseRef] | None:
    path = _release_cache_path(repo, release_path)
    if not path.exists() or time.time() - path.stat().st_mtime > CATALOG_TTL_SECONDS:
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return _parse_releases(spec, data)


def _store_releases(spec: str, repo: str, release_path: str, data: dict) -> None:
    try:
        path = _release_cache_path(repo, release_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
    except Exception:
        pass


def _fetch_releases(spec: str, location: str) -> dict[str, ReleaseRef]:
    """A component's release catalog (its own ``.yak/releases.yml``).

    Read through the Contents API like catalogs — fresh the moment deploy
    commits, cached briefly, and the cache survives across processes (it
    is on disk). The path is derived from the component's catalog
    ``location`` — two components in one repository own independent
    release catalogs. An empty catalog (404) means nothing is published.
    """
    repo = github_repo(spec)
    release_path = release_index_path(location)
    cached = _cached_releases(spec, repo, release_path)
    if cached is not None:
        return cached
    url = f"https://api.github.com/repos/{repo}/contents/{release_path}"
    headers = {"Accept": "application/vnd.github.raw+json"}
    _trace(url)
    try:
        with urlopen(Request(url, headers=headers)) as resp:
            data = yaml.safe_load(resp.read().decode()) or {}
    except HTTPError as exc:
        if exc.code == 404:
            return {}
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    except Exception as exc:
        raise CatalogError(f"cannot fetch {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{url} must be a mapping")
    _store_releases(spec, repo, release_path, data)
    return _parse_releases(spec, data)


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
        _trace(url)
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
    raw_components = data.get("components") or {}
    if not isinstance(raw_components, dict):
        raise CatalogError(
            f"catalog '{spec}': 'components' must be a mapping of "
            "name → location (ADR-23 Step 4)"
        )
    for name, entry in raw_components.items():
        if not isinstance(name, str) or not name:
            raise CatalogError(
                f"catalog '{spec}': component keys must be non-empty names"
            )
        if not isinstance(entry, dict) or not isinstance(entry.get("location"), str):
            raise CatalogError(
                f"catalog '{spec}': component '{name}' needs a 'location'"
            )
        # Only ``location`` is read. The catalog key is a discovery
        # binding only — identity lives in component.yml, and a version /
        # release / digest / distribution never belongs to the catalog.
        # Any other field is ignored for forward compatibility.
        components.append(ComponentRef(name=name, location=entry["location"]))
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

    ``components`` maps a discovery key (the catalog's name → location
    binding, ADR-23 Step 4) to its catalog and reference; ``bundles``
    maps a bundle name to its catalog and member list. First hit wins
    (source order) in both namespaces. The index is built from catalog
    keys only — no component manifest is read during discovery, remote or
    local; identity is validated at the actual materialization.
    """

    components: dict[str, tuple[Catalog, ComponentRef]] = field(default_factory=dict)
    bundles: dict[str, tuple[Catalog, tuple[str, ...]]] = field(default_factory=dict)

    def resolve(self, name: str) -> tuple[Catalog, ComponentRef] | None:
        return self.components.get(name)

    def resolve_bundle(self, name: str) -> tuple[Catalog, tuple[str, ...]] | None:
        return self.bundles.get(name)


def build_index(source_specs: list[str], context_root: Path) -> Index:
    """Merge the declared source catalogs into a flat index.

    The catalog is a ``name → location`` mapping (ADR-23 Step 4). The
    merged index is built directly from those keys — never from a
    per-location ``.yak/component.yml`` fetch, remote or local — so the
    remote index costs O(catalogs/repositories) requests, not O(components).
    The catalog key is a discovery binding only; identity is validated
    against the component's own contract at materialization. Declaration
    order: a component or bundle is taken from the first catalog that
    offers it; later catalogs do not override it. The source list is
    flat — it knows catalog locations, nothing nests.
    """
    components: dict[str, tuple[Catalog, ComponentRef]] = {}
    bundles: dict[str, tuple[Catalog, tuple[str, ...]]] = {}
    for spec in source_specs:
        catalog = load_catalog(spec, context_root)
        for ref in catalog.components:
            components.setdefault(ref.name, (catalog, ref))
        for name, members in catalog.bundles.items():
            bundles.setdefault(name, (catalog, members))
    return Index(components=components, bundles=bundles)
