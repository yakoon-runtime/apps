"""GitHub Release repository — resolve artifacts from GitHub Releases."""

from __future__ import annotations

import json
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

from y5n.apps.yak.resolver.artifact import Artifact, _parse_manifest


class GithubReleaseRepository:
    """Resolve artifacts from a GitHub repository's releases.

    Cache: ~/.yak/cache/github/<owner>/<repo>/<fingerprint>/
    """

    def __init__(self, repo: str) -> None:
        # "owner/repo" or "github:owner/repo"
        self._repo = repo.removeprefix("github:")
        self._cache_root = Path.home() / ".yak" / "cache" / "github" / self._repo

    def resolve(self, name: str) -> Artifact | None:
        # Check cache first
        if self._cache_root.is_dir():
            for entry in self._cache_root.iterdir():
                if not entry.is_dir():
                    continue
                manifest = entry / "artifact.yml"
                if manifest.exists():
                    meta = _parse_manifest(manifest)
                    if meta is not None and meta.get("name") == name:
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
                            path=entry,
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

        # Download and extract to cache
        try:
            with urlopen(asset_url) as resp:
                data = resp.read()
        except Exception:
            return None

        # Extract to temp dir, then read artifact.yml to get fingerprint
        with tempfile.TemporaryDirectory() as tmp:
            tarpath = Path(tmp) / "artifact.tar.gz"
            tarpath.write_bytes(data)
            with tarfile.open(tarpath, "r:gz") as tar:
                tar.extractall(path=tmp)

            # Find artifact.yml in extracted files
            extract_root = Path(tmp)
            for f in extract_root.rglob("artifact.yml"):
                meta = _parse_manifest(f)
                if meta is not None and meta.get("name") == name:
                    fp = meta.get("fingerprint", "")
                    if fp.startswith("sha256:"):
                        fp = fp[7:]
                    # Copy to cache by fingerprint
                    cache_dir = self._cache_root / (fp or name)
                    if not cache_dir.exists():
                        cache_dir.mkdir(parents=True)
                        for src in extract_root.iterdir():
                            dst = cache_dir / src.name
                            if src.is_dir():
                                import shutil

                                shutil.copytree(src, dst, dirs_exist_ok=True)
                            else:
                                dst.write_bytes(src.read_bytes())

                    return Artifact(
                        name=meta["name"],
                        version=meta.get("version", "0"),
                        kind=meta.get("kind", "package"),
                        host=meta.get("host", "python"),
                        builder=meta.get("builder", "python"),
                        dependencies=meta.get("dependencies", []),
                        fingerprint=fp,
                        path=cache_dir,
                    )

        return None
