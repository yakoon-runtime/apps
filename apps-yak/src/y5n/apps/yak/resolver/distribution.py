"""Distribution — what a world can install, served as a plain HTTP object.

ADR-24: ``distribution.yml`` is the consumer-optimized view of an
organization's offering, owned by a distribution (not a component, not a
source repository). The consumer contract is:

- one GET of ``distribution.yml`` (a URL, not GitHub),
- resolve ``(name, version) → {url, digest, dependencies}`` locally,
- download the artifact, verify the digest, install.

The read path never touches Git repositories, ``component.yml`` or the
GitHub Contents API. Dependencies are authoritative in the artifact and
materialized here (ADR-24 Q3) so the dependency graph is computable from
the single metadata fetch.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

from y5n.apps.yak.resolver.catalog import _find_artifact_dir, _sha256_hex


class DistributionError(Exception):
    """A distribution could not be loaded, resolved or verified."""


@dataclass(frozen=True)
class DistributionRelease:
    """One published build a distribution offers.

    ``url`` is a plain HTTP(S) artifact address; ``digest`` is the sha256
    of the downloaded tarball and the consumer's trust anchor.
    ``dependencies`` are materialized from the artifact (ADR-24 Q3).
    """

    version: str
    url: str
    digest: str | None
    dependencies: tuple[str, ...]


class Distribution:
    """A parsed ``distribution.yml`` — materialized, consumer-served index.

    ``components`` maps a component name to its releases (by version);
    ``bundles`` maps a bundle name to its component names. Resolution is a
    local lookup; nothing here contacts a network.
    """

    def __init__(self, url: str, data: dict) -> None:
        self.url = url
        self.components: dict[str, dict[str, DistributionRelease]] = {}
        raw_components = data.get("components") or {}
        if not isinstance(raw_components, dict):
            raise DistributionError(
                f"distribution '{url}': 'components' must be a mapping"
            )
        for name, raw_releases in raw_components.items():
            if not isinstance(raw_releases, dict):
                raise DistributionError(
                    f"distribution '{url}': component '{name}' must be a mapping"
                )
            releases: dict[str, DistributionRelease] = {}
            raw_by_version = raw_releases.get("releases")
            if raw_by_version is None:
                raw_by_version = {}
            if not isinstance(raw_by_version, dict):
                raise DistributionError(
                    f"distribution '{url}': component '{name}' needs a 'releases' mapping"
                )
            for version, entry in raw_by_version.items():
                if not isinstance(entry, dict):
                    raise DistributionError(
                        f"distribution '{url}': release '{name} {version}' must be a mapping"
                    )
                artifact_url = entry.get("url")
                if not isinstance(artifact_url, str) or not artifact_url:
                    raise DistributionError(
                        f"distribution '{url}': release '{name} {version}' needs a 'url'"
                    )
                digest = entry.get("digest")
                if digest is not None and not isinstance(digest, str):
                    raise DistributionError(
                        f"distribution '{url}': release '{name} {version}' digest must be a string"
                    )
                raw_deps = entry.get("dependencies") or []
                deps = (
                    tuple(str(d) for d in raw_deps)
                    if isinstance(raw_deps, list)
                    else ()
                )
                releases[str(version)] = DistributionRelease(
                    version=str(version),
                    url=artifact_url,
                    digest=digest,
                    dependencies=deps,
                )
            self.components[name] = releases

        raw_bundles = data.get("bundles") or {}
        if raw_bundles and not isinstance(raw_bundles, dict):
            raise DistributionError(
                f"distribution '{url}': 'bundles' must be a mapping"
            )
        self.bundles: dict[str, tuple[str, ...]] = {
            str(k): tuple(str(m) for m in v) for k, v in raw_bundles.items()
        }

    def resolve_bundle(self, name: str) -> tuple[str, ...] | None:
        return self.bundles.get(name)

    def has(self, name: str) -> bool:
        return name in self.components

    def latest(self, name: str) -> DistributionRelease | None:
        releases = self.components.get(name)
        if not releases:
            return None
        return max(releases.values(), key=lambda rel: _version_key(rel.version))


def _version_key(version: str) -> tuple:
    parts = []
    for segment in version.replace("-", ".").split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def load_distribution(url: str) -> Distribution:
    """Fetch and parse ``distribution.yml`` over plain HTTP(S).

    The distribution is a static object (raw URL, CDN, local file) — the
    consumer contract is one GET, never a Contents-API crawl.
    """
    try:
        with urlopen(Request(url, headers={"Accept": "application/yaml"})) as resp:
            bytes_ = resp.read()
    except Exception as exc:
        raise DistributionError(f"cannot fetch distribution {url}: {exc}") from exc
    try:
        data = yaml.safe_load(bytes_.decode())
    except Exception as exc:
        raise DistributionError(f"cannot read distribution {url}: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise DistributionError(f"{url} must be a mapping")
    return Distribution(url, data)


def merge_distributions(seq: list[Distribution]) -> Distribution:
    """Merge ordered distributions into one installable universe.

    A context lists distributions in priority order: for an identical
    identity (component or bundle) the **later** distribution wins. There
    is no special default origin — ``runtime`` is simply the bundle found
    in the merged index, wherever it is offered.
    """
    merged = Distribution(
        url=", ".join(d.url for d in seq), data={"components": {}, "bundles": {}}
    )
    for dist in seq:
        merged.components.update(dist.components)
        merged.bundles.update(dist.bundles)
    return merged


def _cache_root(url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    return Path.home() / ".yak" / "cache" / "dist" / digest


def fetch_distribution_artifact(
    url: str,
    name: str,
    digest: str | None,
    cache_root: Path | None = None,
) -> Path | None:
    """Download an artifact from its distribution URL and verify the digest.

    The digest is the consumer's trust anchor (ADR-24): when the recorded
    digest matches, the extracted content is used; otherwise the download
    fails loudly. A verified artifact is cached under its digest.
    """
    cache_root = cache_root or _cache_root(url)
    release_dir = cache_root / name
    if digest is not None and _cached_artifact(release_dir, digest) is not None:
        return _cached_artifact(release_dir, digest)

    try:
        with urlopen(Request(url)) as resp:
            data = resp.read()
    except Exception as exc:
        raise DistributionError(f"cannot fetch artifact {url}: {exc}") from exc
    if digest is not None and _sha256_hex(data) != digest:
        raise DistributionError(
            f"digest mismatch for {name}: distribution records {digest}, "
            f"downloaded {_sha256_hex(data)}"
        )
    with tempfile.TemporaryDirectory() as tmp:
        tarpath = Path(tmp) / f"{name}.artifact.tar.gz"
        tarpath.write_bytes(data)
        try:
            with tarfile.open(tarpath, "r:gz") as tar:
                tar.extractall(path=tmp, filter="data")
        except Exception as exc:
            raise DistributionError(f"cannot extract {url}: {exc}") from exc
        artifact_dir = _find_artifact_dir(Path(tmp))
        if artifact_dir is None:
            raise DistributionError(f"no artifact in {url}")
        return _store_artifact(release_dir, artifact_dir, digest)


def _cached_artifact(release_dir: Path, digest: str) -> Path | None:
    manifest = release_dir / "manifest.json"
    if not manifest.exists():
        return None
    try:
        meta = json.loads(manifest.read_text())
    except Exception:
        return None
    if meta.get("digest") != digest:
        return None
    artifact_dir = _find_artifact_dir(release_dir / "artifact")
    return artifact_dir


def _store_artifact(release_dir: Path, artifact_dir: Path, digest: str | None) -> Path:
    store = release_dir / "artifact"
    if store.exists():
        shutil.rmtree(store, ignore_errors=True)
    store.mkdir(parents=True, exist_ok=True)
    shutil.copytree(artifact_dir, store / artifact_dir.name)
    (release_dir / "manifest.json").write_text(json.dumps({"digest": digest}))
    return store / artifact_dir.name
