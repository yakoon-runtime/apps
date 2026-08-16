"""M2 acceptance: deploy makes a published artifact available remotely.

Contract:

    yak deploy <component> --to <repository>
        precondition:  component is published locally (~/.yak/artifacts/)
        postcondition: repository.resolve(component) can retrieve it

GitHub is mocked at the HTTP layer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from pathlib import Path
from urllib.error import HTTPError

from conftest import make_source
from y5n.apps.yak.publisher.publish import deploy_artifact
from y5n.apps.yak.resolver.github import GithubReleaseRepository


class _FakeResp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


class _FakeRequest:
    def __init__(self, url, data=None, headers=None, method=None) -> None:
        self.full_url = url
        self.data = data
        self.headers = headers or {}
        self.method = method


class FakeGithub:
    """A minimal GitHub Releases API: releases hold named assets."""

    def __init__(self) -> None:
        self.releases: dict[str, dict] = {}
        self.uploaded_assets: list[str] = []
        self._next_id = 1
        self.catalog_content: bytes | None = None
        self.catalog_sha = "sha-catalog"
        self.fail_catalog = False
        self.catalog_path: str | None = None

    def _release(self, repo: str) -> dict | None:
        return self.releases.get(repo)

    def _upload_url(self, repo: str, rid: int) -> str:
        return f"https://uploads.gh/repos/{repo}/releases/{rid}/assets"

    def _assets(self, repo: str, release: dict) -> list[dict]:
        return [
            {
                "id": aid,
                "name": name,
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "browser_download_url": (
                    f"https://gh/{repo}/dl/{release['tag']}/{name}"
                ),
            }
            for name, (aid, data) in release["assets"].items()
        ]

    def urlopen(self, url):
        full = url.full_url if hasattr(url, "full_url") else str(url)
        method = getattr(url, "method", "GET") or "GET"
        data = getattr(url, "data", None)

        if "/releases?" in full:
            repo = full.split("/repos/", 1)[1].split("/releases", 1)[0]
            release = self._release(repo)
            releases = []
            if release is not None:
                releases.append(
                    {"tag_name": release["tag"], "assets": self._assets(repo, release)}
                )
            return _FakeResp(json.dumps(releases).encode())

        if "/releases/latest" in full:
            repo = full.split("/repos/", 1)[1].split("/releases", 1)[0]
            release = self._release(repo)
            if release is None:
                raise OSError("no release")
            assets = [
                {
                    "name": name,
                    "browser_download_url": (
                        f"https://gh/{repo}/dl/{release['tag']}/{name}"
                    ),
                }
                for name in release["assets"]
            ]
            return _FakeResp(json.dumps({"assets": assets}).encode())

        if "/releases/tags/" in full:
            repo = full.split("/repos/", 1)[1].split("/releases/tags/", 1)[0]
            tag = full.split("/releases/tags/", 1)[1]
            release = self._release(repo)
            if release is None or release["tag"] != tag:
                raise OSError("no release")
            return _FakeResp(
                json.dumps(
                    {
                        "id": release["id"],
                        "tag_name": release["tag"],
                        "assets": self._assets(repo, release),
                        "upload_url": self._upload_url(repo, release["id"])
                        + "{?name,label}",
                    }
                ).encode()
            )

        if full.endswith("/releases") and method == "POST":
            repo = full.split("/repos/", 1)[1].split("/releases", 1)[0]
            body = json.loads((data or b"").decode())
            assert body["draft"] is False, "deploy must publish, not draft"
            rid = self._next_id
            self._next_id += 1
            self.releases[repo] = {"id": rid, "tag": body["tag_name"], "assets": {}}
            return _FakeResp(
                json.dumps(
                    {
                        "id": rid,
                        "upload_url": self._upload_url(repo, rid) + "{?name,label}",
                    }
                ).encode()
            )

        if "/releases/" in full and method == "PATCH":
            repo = full.split("/repos/", 1)[1].split("/releases/", 1)[0]
            rid = int(full.rsplit("/", 1)[1])
            release = self._release(repo)
            assert release is not None and release["id"] == rid
            return _FakeResp(
                json.dumps(
                    {
                        "id": rid,
                        "tag_name": release["tag"],
                        "upload_url": self._upload_url(repo, rid) + "{?name,label}",
                    }
                ).encode()
            )

        if "/assets" in full and method == "GET":
            repo = full.split("/repos/", 1)[1].split("/releases/", 1)[0]
            release = self._release(repo)
            assert release is not None
            return _FakeResp(json.dumps(self._assets(repo, release)).encode())

        if "/assets" in full and method == "POST":
            repo = full.split("/repos/", 1)[1].split("/releases/", 1)[0]
            name = full.split("name=", 1)[1]
            release = self._release(repo)
            assert release is not None
            aid = self._next_id
            self._next_id += 1
            release["assets"][name] = (aid, data)
            self.uploaded_assets.append(name)
            return _FakeResp(b"{}")

        if "/releases/assets/" in full and method == "DELETE":
            aid = int(full.rsplit("/", 1)[1])
            for release in self.releases.values():
                for name, (asset_id, _bytes) in list(release["assets"].items()):
                    if asset_id == aid:
                        del release["assets"][name]
                        return _FakeResp(b"{}")
            raise OSError("no asset")

        if "/dl/" in full:
            name = full.rsplit("/", 1)[1]
            for release in self.releases.values():
                if name in release["assets"]:
                    return _FakeResp(release["assets"][name][1])
            raise OSError("asset not found")

        if "/contents/" in full:
            repo = full.split("/repos/", 1)[1].split("/contents/", 1)[0]
            path = full.split("/contents/", 1)[1]
            contents_url = f"https://api.github.com/repos/{repo}/contents/{path}"
            is_catalog = path.endswith("catalog.yml")
            if not is_catalog or method == "GET":
                if self.catalog_content is None:
                    raise HTTPError(contents_url, 404, "Not Found", {}, None)
                return _FakeResp(
                    json.dumps(
                        {
                            "path": path,
                            "content": base64.b64encode(self.catalog_content).decode(),
                            "sha": self.catalog_sha,
                        }
                    ).encode()
                )
            body = json.loads((data or b"").decode())
            if self.fail_catalog:
                raise HTTPError(contents_url, 500, "Internal Server Error", {}, None)
            self.catalog_content = base64.b64decode(body["content"])
            self.catalog_sha = f"sha-{len(self.catalog_content)}"
            self.catalog_path = path
            return _FakeResp(
                json.dumps({"path": path, "sha": self.catalog_sha}).encode()
            )

        raise AssertionError(f"unexpected request: {full}")


def _published_artifact(home: Path) -> Path:
    store = home / ".yak" / "artifacts" / "crm-1.0.0.python.artifact"
    (store / "structure").mkdir(parents=True)
    (store / "structure" / "x.txt").write_text("data")
    (store / "artifact.yml").write_text(
        "name: crm\n"
        "version: 1.0.0\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        "mount: /opt/contacts\n"
        "fingerprint: sha256:abc123\n"
    )
    return store


def _mock_home(monkeypatch, tmp: str) -> Path:
    home = Path(tmp) / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home


def _mock_github(monkeypatch) -> FakeGithub:
    fake = FakeGithub()
    monkeypatch.setattr("y5n.apps.yak.resolver.github.urlopen", fake.urlopen)
    monkeypatch.setattr("y5n.apps.yak.resolver.github.Request", _FakeRequest)
    monkeypatch.setenv("YAK_GITHUB_TOKEN", "test-token")
    return fake


def test_deploy_is_not_draft(monkeypatch):
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)
        GithubReleaseRepository("acme/packs").deploy("crm", store)
        assert fake.releases["acme/packs"]["tag"] == "crm-v1.0.0"


def test_redeploy_same_version_is_noop_until_content_changes(monkeypatch):
    """Same build → NO-OP; a changed build of the same version → REPLACE."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)

        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("crm", store) is True
        release_id = fake.releases["acme/packs"]["id"]
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 1

        # Same build again: no-op — the release stays, no re-upload.
        assert repo.deploy("crm", store) is True
        assert fake.releases["acme/packs"]["id"] == release_id
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 1

        # A changed build of the same version: the asset is replaced, the
        # release itself is never recreated.
        (store / "structure" / "x.txt").write_text("changed")
        assert repo.deploy("crm", store) is True
        assert fake.releases["acme/packs"]["id"] == release_id
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 2


def test_deploy_artifact_requires_published(monkeypatch):
    _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        result = deploy_artifact("crm", "github:acme/packs")
        assert result is None


def test_deploy_spec_with_catalog_path_writes_that_catalog(monkeypatch):
    """A source spec carrying a catalog path deploys into that catalog."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        repo = GithubReleaseRepository("github:acme/packs:packs/catalog.yml")
        assert repo.deploy("ident", _published(home, "ident", "1.0.0")) is True
        assert fake.catalog_path == "packs/catalog.yml"
        assert set(_catalog_entries(fake)) == {"ident"}
        assert _catalog_entries(fake)["ident"] == {
            "location": "ident",
        }


def test_distribution_comes_from_the_context(monkeypatch):
    """Without --to, deploy targets the context's distribution repository."""
    from y5n.apps.yak.hosts.cli.cwd import Context
    from y5n.apps.yak.installation.manager import InstallationManager
    from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
    from y5n.apps.yak.repository.file_repo import FileRepository

    _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        make_source(
            repo,
            {"cool-shell": {"location": "cool-shell"}},
        )
        ctx = Context(
            path=root,
            sources=[str(repo)],
            distribution="github:acme/dists",
        )
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        assert mgr._distribution_spec() == "github:acme/dists"
        assert InstallationManager(FileRepository(), DirectoryArtifactStore())._distribution_spec() is None


def _published(home: Path, name: str, version: str, mount: str = "/opt/x") -> Path:
    store = home / ".yak" / "artifacts" / f"{name}-{version}.python.artifact"
    (store / "structure").mkdir(parents=True, exist_ok=True)
    (store / "structure" / "x.txt").write_text("data")
    (store / "artifact.yml").write_text(
        "name: " + name + "\n"
        "version: " + version + "\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        "mount: " + mount + "\n"
        "fingerprint: sha256:" + version + "\n"
    )
    return store


def _catalog_entries(fake) -> dict:
    if fake.catalog_content is None:
        return {}
    import yaml

    return (yaml.safe_load(fake.catalog_content) or {}).get("components", {})


def test_j_deploy_preserves_existing_catalog_entries(monkeypatch):
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("system", _published(home, "system", "1.0.0")) is True
        assert set(_catalog_entries(fake)) == {"system"}
        assert repo.deploy("ident", _published(home, "ident", "1.0.0")) is True
        assert set(_catalog_entries(fake)) == {"system", "ident"}


def test_k_redeploy_is_idempotent(monkeypatch):
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("ident", _published(home, "ident", "1.0.0")) is True
        assert repo.deploy("ident", _published(home, "ident", "1.0.0")) is True
        entries = _catalog_entries(fake)
        assert list(entries) == ["ident"]
        # The catalog stays a dumb Name → Location map — no version truth.
        assert entries["ident"] == {"location": "ident"}


def test_l_new_version_updates_the_single_entry(monkeypatch):
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("ident", _published(home, "ident", "1.0.0")) is True
        assert repo.deploy("ident", _published(home, "ident", "2.0.0")) is True
        entries = _catalog_entries(fake)
        assert list(entries) == ["ident"]
        # A new version never touches the catalog — the version lives in
        # the repository, not in the catalog.
        assert entries["ident"] == {"location": "ident"}


def test_m_failed_catalog_update_keeps_old_catalog_valid(monkeypatch):
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("system", _published(home, "system", "1.0.0")) is True
        assert "system" in _catalog_entries(fake)

        fake.fail_catalog = True
        assert repo.deploy("ident", _published(home, "ident", "1.0.0")) is False
        # The old catalog stays valid — it never points at the new artifact.
        assert set(_catalog_entries(fake)) == {"system"}
