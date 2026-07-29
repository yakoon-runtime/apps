"""GitHub Release repository — resolve artifacts from GitHub Releases."""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

from y5n.apps.yak.resolver.artifact import Artifact, _parse_manifest


class GithubReleaseRepository:
    """Resolve artifacts from a GitHub repository's releases.

    Cache: ~/.yak/cache/github/<owner>/<repo>/<fingerprint>/<artifact_name>/
    """

    def __init__(self, repo: str) -> None:
        self._repo = repo.removeprefix("github:")
        self._cache_root = Path.home() / ".yak" / "cache" / "github" / self._repo

    def _find_artifact_dir(self, parent: Path, name: str) -> Path | None:
        """Find the artifact subdirectory containing artifact.yml for `name`."""
        for child in parent.iterdir():
            if not child.is_dir():
                continue
            manifest = child / "artifact.yml"
            if manifest.exists():
                meta = _parse_manifest(manifest)
                if meta is not None and meta.get("name") == name:
                    return child
        return None

    def resolve(self, name: str) -> Artifact | None:
        # Check cache first
        if self._cache_root.is_dir():
            for fp_dir in self._cache_root.iterdir():
                if not fp_dir.is_dir():
                    continue
                artifact_dir = self._find_artifact_dir(fp_dir, name)
                if artifact_dir is not None:
                    meta = _parse_manifest(artifact_dir / "artifact.yml")
                    fp = meta.get("fingerprint", "")
                    if fp.startswith("sha256:"):
                        fp = fp[7:]
                    return Artifact(
                        name=meta["name"],
                        version=meta.get("version", "0"),
                        kind=meta.get("kind", "package"),
                        host=meta.get("host", "python"),
                        builder=meta.get("builder", "python"),
                        dependencies=meta.get("dependencies", []),
                        fingerprint=fp,
                        path=artifact_dir,
                    )

        # Fetch latest release from GitHub API
        url = f"https://api.github.com/repos/{self._repo}/releases/latest"
        try:
            with urlopen(url) as resp:
                release = json.loads(resp.read().decode())
        except Exception:
            return None

        # Find asset matching artifact name
        assets = release.get("assets", [])
        target_name = f"{name}.artifact.tar.gz"
        asset_url = None
        for asset in assets:
            if asset["name"] == target_name:
                asset_url = asset["browser_download_url"]
                break

        if asset_url is None:
            return None

        # Download asset
        try:
            with urlopen(asset_url) as resp:
                data = resp.read()
        except Exception:
            return None

        # Extract and cache
        with tempfile.TemporaryDirectory() as tmp:
            tarpath = Path(tmp) / "artifact.tar.gz"
            tarpath.write_bytes(data)
            with tarfile.open(tarpath, "r:gz") as tar:
                tar.extractall(path=tmp)

            # Find the artifact dir (contains artifact.yml)
            artifact_dir = self._find_artifact_dir(Path(tmp), name)
            if artifact_dir is None:
                return None

            meta = _parse_manifest(artifact_dir / "artifact.yml")
            fp = meta.get("fingerprint", "")
            if fp.startswith("sha256:"):
                fp = fp[7:]

            # Cache by fingerprint
            cache_fp_dir = self._cache_root / (fp or name)
            cache_fp_dir.mkdir(parents=True, exist_ok=True)
            cached = cache_fp_dir / artifact_dir.name
            if not cached.exists():
                shutil.copytree(artifact_dir, cached)

            return Artifact(
                name=meta["name"],
                version=meta.get("version", "0"),
                kind=meta.get("kind", "package"),
                host=meta.get("host", "python"),
                builder=meta.get("builder", "python"),
                dependencies=meta.get("dependencies", []),
                fingerprint=fp,
                path=cached,
            )
