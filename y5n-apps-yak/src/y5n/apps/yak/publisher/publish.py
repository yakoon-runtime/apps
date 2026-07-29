"""Publish artifacts to local store or remote repositories."""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from y5n.apps.yak.resolver.artifact import DirectorySource
from y5n.apps.yak.resolver.install import _collect_roots


def _find_artifact(name: str) -> Path | None:
    """Find artifact in context-local .yak/artifacts/."""
    for root in _collect_roots(None):
        source = DirectorySource(root)
        artifact = source.resolve(name)
        if artifact is not None and artifact.path is not None:
            return artifact.path
    return None


def publish_local(name: str) -> Path | None:
    """Copy artifact to ~/.yak/artifacts/."""
    src = _find_artifact(name)
    if src is None:
        return None

    target_dir = Path.home() / ".yak" / "artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / src.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def publish_github(name: str, repo: str, draft: bool = True) -> bool:
    """Upload artifact as a GitHub Release asset.

    Requires GITHUB_TOKEN environment variable.
    repo format: "owner/repo" or "github:owner/repo"
    """
    repo = repo.removeprefix("github:")
    token = os.environ.get("YAK_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  GITHUB_TOKEN not set")
        return False

    src = _find_artifact(name)
    if src is None:
        return False

    # Create tar.gz in temp dir
    with tempfile.TemporaryDirectory() as tmp:
        tarpath = Path(tmp) / f"{name}.artifact.tar.gz"
        with tarfile.open(tarpath, "w:gz") as tar:
            tar.add(src, arcname=src.name)

        # Get or create release
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Extract version from dir name "y5n-apps-yak-0.1.0.python.artifact" → "0.1.0"
        suffix = src.name.replace(f"{name}-", "")
        version_part = suffix.rsplit(".", 2)[0]  # remove .python.artifact
        tag = f"{name}-v{version_part}"

        # Check if a release with this tag already exists (e.g. draft from previous run)
        release = None
        get_req = Request(
            f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
            headers=headers,
            method="GET",
        )
        try:
            with urlopen(get_req) as resp:
                release = json.loads(resp.read().decode())
        except Exception:
            pass

        if release:
            # Update existing release
            release_id = release["id"]
            release_data = {
                "tag_name": tag,
                "name": f"{name} {tag.removeprefix(name + '-')}",
                "draft": draft,
            }
            req = Request(
                f"https://api.github.com/repos/{repo}/releases/{release_id}",
                data=json.dumps(release_data).encode(),
                headers=headers,
                method="PATCH",
            )
        else:
            # Create new release
            release_data = {
                "tag_name": tag,
                "name": f"{name} {tag.removeprefix(name + '-')}",
                "draft": draft,
            }
            req = Request(
                f"https://api.github.com/repos/{repo}/releases",
                data=json.dumps(release_data).encode(),
                headers=headers,
                method="POST",
            )

        try:
            with urlopen(req) as resp:
                release = json.loads(resp.read().decode())
        except Exception as e:
            print(f"  Failed to create/update release: {e}")
            return False

        release_id = release.get("id")
        upload_url = release.get("upload_url", "").split("{")[0]

        # Upload asset
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
                print(f"  Published {name} to {repo} release {tag}")
                return True
        except Exception as e:
            print(f"  Failed to upload asset: {e}")
            return False


def publish_artifact(name: str, target: str | None = None) -> Path | bool | None:
    """Publish artifact. target can be a path or 'github:owner/repo'."""
    if target and target.startswith("github:"):
        draft = "?release" not in target
        repo = target.split("?")[0]
        ok = publish_github(name, repo, draft=draft)
        return ok
    return publish_local(name)
