"""GitHub Release repository — receive deployed resources (ADR-20)."""

from __future__ import annotations

import base64
import json
import os
import tarfile
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml


class GithubReleaseRepository:
    """A GitHub source: serves a catalog and receives deployed resources.

    Resolution lives in the catalog/index (ADR-20); this adapter is
    transport: it fetches the declared catalog and serves resources, and
    on the write side it publishes an artifact plus its catalog entry.

    The catalog stays minimal — ``ComponentName → relative Location``.
    ``deploy`` only ensures the entry exists (``name → name``); it never
    writes version, fingerprint or release paths into the catalog.
    """

    def __init__(self, repo: str) -> None:
        self._repo = repo.removeprefix("github:")

    def deploy(self, name: str, artifact_dir: Path, *, draft: bool = False) -> bool:
        """Publish a resource and its catalog entry (ADR-20).

        One repository operation: the artifact is fully published first,
        then the catalog entry is ensured as the last step. The entry is
        minimal — ``name → name`` (relative location in the repo) — the
        catalog never learns about versions, fingerprints or releases.
        Failing the artifact upload leaves the old catalog valid; failing
        the catalog update leaves the artifact unreferenced but the old
        catalog valid. Requires GITHUB_TOKEN or YAK_GITHUB_TOKEN.
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

            # Extract "0.1.0" from "crm-0.1.0.python.artifact" for the tag.
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
            except Exception as exc:
                print(f"  Failed to upload asset: {exc}")
                return False

            # Catalog entry is the last step: the resource becomes
            # resolvable only once the catalog knows it. The entry is
            # minimal — the component's relative location in the repo.
            if not self._upsert_catalog(name, headers):
                print(f"  Deploy failed: catalog not updated for {name}")
                return False
            return True

    def _upsert_catalog(self, name: str, headers: dict) -> bool:
        """Ensure the component's minimal entry in the repository's catalog.yml.

        Reads the current catalog from the default branch, adds or
        replaces ``name → name`` (the component's relative location) and
        commits it back. Existing entries are preserved. The catalog is a
        dumb Name → Location map — no versions, no fingerprints.
        """
        url = f"https://api.github.com/repos/{self._repo}/contents/catalog.yml"
        existing = None
        try:
            with urlopen(Request(url, headers=headers)) as resp:
                existing = json.loads(resp.read().decode())
        except HTTPError as exc:
            if exc.code != 404:
                print(f"  GitHub API error: {exc}")
                return False
        except Exception as exc:
            print(f"  GitHub API error: {exc}")
            return False

        if existing is not None:
            try:
                content = base64.b64decode(existing["content"]).decode()
                catalog = yaml.safe_load(content) or {}
            except Exception as exc:
                print(f"  catalog.yml unreadable: {exc}")
                return False
            if not isinstance(catalog, dict):
                catalog = {}
        else:
            catalog = {}

        components = catalog.setdefault("components", {})
        components[name] = {"location": name}
        new_content = yaml.safe_dump(catalog, default_flow_style=False, sort_keys=False)
        put_data = {
            "message": f"catalog: upsert {name}",
            "content": base64.b64encode(new_content.encode()).decode(),
        }
        if existing is not None and "sha" in existing:
            put_data["sha"] = existing["sha"]
        req = Request(
            url,
            data=json.dumps(put_data).encode(),
            headers=headers,
            method="PUT",
        )
        try:
            with urlopen(req) as resp:
                print(f"  Catalog updated: {name}")
                return True
        except HTTPError as exc:
            print(f"  GitHub API error: {exc}")
            return False
        except Exception as exc:
            print(f"  GitHub API error: {exc}")
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
