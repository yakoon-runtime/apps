"""GitHub Release repository — publish an artifact as a release asset.

The write side of distribution: an artifact becomes physically available
under its deterministic tag (ADR-24). Entering a published build into a
*distribution* (what is installable) is the distribution write — this
adapter only publishes the physical asset and never writes into a source
repository or a component release file.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from y5n.apps.yak.resolver.catalog import _split_spec


def release_tag_for(name: str, artifact_dir: Path) -> str:
    """The release tag for a built artifact — its deploy reference.

    The tag version is derived from the artifact directory name
    (``<name>-<version>.<builder>.artifact``), which the builder names
    from the wheel's own version. Extract ``"0.1.0"`` from
    ``crm-0.1.0.python.artifact``.
    """
    version_part = artifact_dir.name.replace(f"{name}-", "").rsplit(".", 2)[0]
    return f"{name}-v{version_part}"


def _write_artifact_tarball(tarpath: Path, artifact_dir: Path, name: str) -> None:
    """Write the deterministic artifact tarball (``{name}.artifact.tar.gz``).

    Deterministic on purpose: the tarball's digest is the no-op signal for
    ``deploy``, so the gzip header must not carry a timestamp. Same
    artifact content always yields the same digest.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        tar.add(artifact_dir, arcname=artifact_dir.name)
    with open(tarpath, "wb") as fh:
        fh.write(gzip.compress(buf.getvalue(), mtime=0))


def _sha256_digest(data: bytes) -> str:
    """The digest in GitHub's asset format: ``sha256:<hex>``."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _asset_digest(release: dict, asset_name: str) -> str | None:
    """The GitHub digest of a release's named asset, or None."""
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            return asset.get("digest")
    return None


class GithubReleaseRepository:
    """A GitHub repository: serves a catalog and receives deployed releases.

    Resolution lives in the catalog / component release (ADR-20, ADR-23
    Step 4); this adapter is transport. On the write side it publishes an
    artifact as a release with its deterministic asset and updates the
    component's ``.yak/release.yml`` so the read side resolves the new
    build. The component is already discoverable through its own source
    catalog — no catalog is rewritten during deploy.
    """

    def __init__(self, spec: str) -> None:
        self._spec = spec
        _, location, _catalog_path = _split_spec(spec)
        self._repo = location.removeprefix("github:")

    def deploy(self, name: str, artifact_dir: Path, *, draft: bool = False) -> bool:
        """Publish an artifact as a GitHub release asset (physical).

        ``deploy`` makes the artifact physically available under its
        deterministic tag — one repository operation with three outcomes:

        - CREATE: no release for ``{name}-v{version}`` yet — the release
          is created and the asset uploaded.
        - NO-OP: the release exists and its asset digest equals the local
          tarball — nothing changes.
        - REPLACE: the release exists but the asset differs — only the
          asset is replaced, the release itself is never deleted.

        Entering the published build into a *distribution* (what is
        installable) is the distribution write (ADR-24) — this adapter only
        publishes the physical asset and never writes into a source
        repository.

        Requires YAK_GITHUB_TOKEN — the only credential yak ever reads,
        and only on the write path.
        """
        token = os.environ.get("YAK_GITHUB_TOKEN")
        if not token:
            print("  YAK_GITHUB_TOKEN not set")
            return False

        with tempfile.TemporaryDirectory() as tmp:
            tarpath = Path(tmp) / f"{name}.artifact.tar.gz"
            _write_artifact_tarball(tarpath, artifact_dir, name)
            digest = _sha256_digest(tarpath.read_bytes())

            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            }
            tag = release_tag_for(name, artifact_dir)
            asset_name = f"{name}.artifact.tar.gz"

            release = self._release_by_tag(tag, headers)
            if release is not None:
                if _asset_digest(release, asset_name) == digest:
                    print(f"  {name} unchanged on {self._repo} release {tag} (no-op)")
                else:
                    release = self._patch_release(
                        release["id"], name, tag, draft, headers
                    )
                    if release is None:
                        return False
                    self._delete_asset(release["id"], asset_name, headers)
                    if not self._upload_asset(release, name, tarpath, headers, tag):
                        return False
            else:
                release = self._create_release(name, tag, draft, headers)
                if release is None:
                    return False
                if not self._upload_asset(release, name, tarpath, headers, tag):
                    return False

            return True

    def _create_release(
        self, name: str, tag: str, draft: bool, headers: dict
    ) -> dict | None:
        """Create the release for a tag; return it, or None on failure."""
        release_data = {
            "tag_name": tag,
            "name": f"{name} {tag.removeprefix(name + '-v')}",
            "draft": draft,
        }
        req = Request(
            f"https://api.github.com/repos/{self._repo}/releases",
            data=json.dumps(release_data).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            self._api_error(exc)
            return None

    def _patch_release(
        self, release_id: int, name: str, tag: str, draft: bool, headers: dict
    ) -> dict | None:
        """Update an existing release's metadata; return it, or None."""
        release_data = {
            "tag_name": tag,
            "name": f"{name} {tag.removeprefix(name + '-v')}",
            "draft": draft,
        }
        req = Request(
            f"https://api.github.com/repos/{self._repo}/releases/{release_id}",
            data=json.dumps(release_data).encode(),
            headers=headers,
            method="PATCH",
        )
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            self._api_error(exc)
            return None

    def _upload_asset(
        self, release: dict, name: str, tarpath: Path, headers: dict, tag: str
    ) -> bool:
        """Upload the artifact tarball to a release; return success."""
        upload_url = release.get("upload_url", "").split("{")[0]
        if not upload_url:
            return False
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

    @staticmethod
    def _api_error(exc: Exception) -> None:
        body = exc.read().decode(errors="replace") if isinstance(exc, HTTPError) else ""
        print(f"  GitHub API error: {exc}")
        if body:
            print(f"  {body}")

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
