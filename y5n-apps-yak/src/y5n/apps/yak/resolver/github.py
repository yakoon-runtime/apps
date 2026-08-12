"""GitHub Release repository — resolve and deploy artifacts."""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from y5n.apps.yak.resolver.artifact import Artifact, _parse_manifest


class GithubReleaseRepository:
    """Resolve and deploy artifacts from a GitHub repository's releases.

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
                tar.extractall(path=tmp, filter="data")

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

    def deploy(self, name: str, artifact_dir: Path, *, draft: bool = False) -> bool:
        """Ship an artifact into this repository as a release asset.

        Packages ``artifact_dir`` as ``<name>.artifact.tar.gz`` and
        publishes it (non-draft by default) so that ``resolve(name)`` can
        retrieve it immediately. Deploying the same version again updates
        the existing release (idempotent). Requires GITHUB_TOKEN or
        YAK_GITHUB_TOKEN.
        """
        token = os.environ.get("YAK_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("  GITHUB_TOKEN not set")
            return False

        with tempfile.TemporaryDirectory() as tmp:
            tarpath = Path(tmp) / f"{name}.artifact.tar.gz"
            with tarfile.open(tarpath, "w:gz") as tar:
                tar.add(artifact_dir, arcname=artifact_dir.name)

            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            }

            # Extract "0.1.0" from "crm-0.1.0.python.artifact"
            version_part = artifact_dir.name.replace(f"{name}-", "").rsplit(".", 2)[0]
            tag = f"{name}-v{version_part}"
            release_data = {
                "tag_name": tag,
                "name": f"{name} {version_part}",
                "draft": draft,
            }

            release = self._release_by_tag(tag, headers)
            if release is not None:
                # Same version already deployed → update the release.
                req = Request(
                    f"https://api.github.com/repos/{self._repo}/releases/{release['id']}",
                    data=json.dumps(release_data).encode(),
                    headers=headers,
                    method="PATCH",
                )
                try:
                    with urlopen(req) as resp:
                        release = json.loads(resp.read().decode())
                except HTTPError as exc:
                    body = exc.read().decode(errors="replace")
                    print(f"  GitHub API error: {exc}")
                    if body:
                        print(f"  {body}")
                    return False
                except Exception as exc:
                    print(f"  GitHub API error: {exc}")
                    return False
            else:
                req = Request(
                    f"https://api.github.com/repos/{self._repo}/releases",
                    data=json.dumps(release_data).encode(),
                    headers=headers,
                    method="POST",
                )
                try:
                    with urlopen(req) as resp:
                        release = json.loads(resp.read().decode())
                except HTTPError as exc:
                    body = exc.read().decode(errors="replace")
                    print(f"  GitHub API error: {exc}")
                    if body:
                        print(f"  {body}")
                    return False
                except Exception as exc:
                    print(f"  GitHub API error: {exc}")
                    return False

            self._delete_asset(release["id"], f"{name}.artifact.tar.gz", headers)

            upload_url = release.get("upload_url", "").split("{")[0]
            asset_data = tarpath.read_bytes()
            asset_headers = {
                **headers,
                "Content-Type": "application/gzip",
                "Content-Length": str(len(asset_data)),
            }
            asset_name = f"{name}.artifact.tar.gz"
            upload_req = Request(
                f"{upload_url}?name={asset_name}",
                data=asset_data,
                headers=asset_headers,
                method="POST",
            )
            try:
                with urlopen(upload_req) as resp:
                    print(f"  Deployed {name} to {self._repo} release {tag}")
                    return True
            except Exception as exc:
                print(f"  Failed to upload asset: {exc}")
                return False

    def _release_by_tag(self, tag: str, headers: dict) -> dict | None:
        """Return the release for a tag, or None when it does not exist."""
        req = Request(
            f"https://api.github.com/repos/{self._repo}/releases/tags/{tag}",
            headers=headers,
        )
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        except Exception:
            return None

    def _delete_asset(self, release_id: int, asset_name: str, headers: dict) -> None:
        """Delete an asset with the given name from a release, if present."""
        req = Request(
            f"https://api.github.com/repos/{self._repo}/releases/{release_id}/assets",
            headers=headers,
        )
        try:
            with urlopen(req) as resp:
                assets = json.loads(resp.read().decode())
        except Exception:
            return
        for asset in assets:
            if asset.get("name") != asset_name:
                continue
            del_req = Request(
                f"https://api.github.com/repos/{self._repo}/releases/assets/{asset['id']}",
                headers=headers,
                method="DELETE",
            )
            try:
                with urlopen(del_req) as resp:
                    return
            except Exception:
                return
