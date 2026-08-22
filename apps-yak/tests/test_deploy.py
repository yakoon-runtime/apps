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
import types
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
        # The component-local release catalogs: path -> raw bytes.
        self.releases_yml: dict[str, bytes] = {}
        self.releases_yml_sha: dict[str, str] = {}
        self.releases_yml_writes: dict[str, int] = {}

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
            if path.endswith("releases.yml"):
                if method == "GET":
                    content = self.releases_yml.get(path)
                    if content is None:
                        raise HTTPError(contents_url, 404, "Not Found", {}, None)
                    return _FakeResp(
                        json.dumps(
                            {
                                "path": path,
                                "content": base64.b64encode(content).decode(),
                                "encoding": "base64",
                                "sha": self.releases_yml_sha.get(path),
                            }
                        ).encode()
                    )
                if method == "PUT":
                    body = json.loads((data or b"").decode())
                    self.releases_yml[path] = base64.b64decode(body["content"])
                    self.releases_yml_sha[path] = f"sha-{len(self.releases_yml[path])}"
                    self.releases_yml_writes[path] = (
                        self.releases_yml_writes.get(path, 0) + 1
                    )
                    return _FakeResp(
                        json.dumps(
                            {"path": path, "sha": self.releases_yml_sha[path]}
                        ).encode()
                    )
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
        GithubReleaseRepository("acme/packs").deploy("crm", store, location="contacts")
        assert fake.releases["acme/packs"]["tag"] == "crm-v1.0.0"


def test_redeploy_same_version_is_noop_until_content_changes(monkeypatch):
    """Same build → NO-OP; a changed build of the same version → REPLACE."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)

        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("crm", store, location="contacts") is True
        release_id = fake.releases["acme/packs"]["id"]
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 1

        # Same build again: no-op — the release stays, no re-upload.
        assert repo.deploy("crm", store, location="contacts") is True
        assert fake.releases["acme/packs"]["id"] == release_id
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 1

        # A changed build of the same version: the asset is replaced, the
        # release itself is never recreated.
        (store / "structure" / "x.txt").write_text("changed")
        assert repo.deploy("crm", store, location="contacts") is True
        assert fake.releases["acme/packs"]["id"] == release_id
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 2


def test_deploy_artifact_requires_published(monkeypatch):
    _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        result = deploy_artifact("crm", "github:acme/packs")
        assert result is None


def test_deploy_registers_release_in_component_local_catalog(monkeypatch):
    """deploy registers the build in the component's .yak/releases.yml —
    component-local, keyed by version, tag + digest only."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)

        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("crm", store, location="contacts") is True

        rp = "contacts/.yak/releases.yml"
        assert rp in fake.releases_yml
        assert set(fake.releases_yml) == {rp}  # strictly component-local
        assert fake.releases_yml_writes[rp] == 1

        content = fake.releases_yml[rp].decode()
        assert "1.0.0:" in content  # version is the release key
        assert "tag: crm-v1.0.0" in content
        # The digest is the sha256 of the published tarball — the concrete
        # build identity (version alone does not identify a build).
        tarball = fake.releases["acme/packs"]["assets"]["crm.artifact.tar.gz"][1]
        expected_digest = "sha256:" + hashlib.sha256(tarball).hexdigest()
        assert f"digest: {expected_digest}" in content
        # The catalog owns published builds only — no second authority.
        assert "components" not in content
        assert "name:" not in content


def test_redeploy_same_build_is_noop_including_release_catalog(monkeypatch):
    """An unchanged artifact stays a NO-OP: no re-upload, no re-write of
    releases.yml (the version already records exactly that build)."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)
        rp = "contacts/.yak/releases.yml"

        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("crm", store, location="contacts") is True
        release_id = fake.releases["acme/packs"]["id"]
        writes_after_first = fake.releases_yml_writes[rp]
        assert writes_after_first == 1

        # Same build again: the release and the release catalog stay as-is.
        assert repo.deploy("crm", store, location="contacts") is True
        assert fake.releases["acme/packs"]["id"] == release_id
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 1
        assert fake.releases_yml_writes[rp] == writes_after_first

        # A changed build of the same version: the asset is replaced and
        # the release catalog is updated to the new digest.
        (store / "structure" / "x.txt").write_text("changed")
        assert repo.deploy("crm", store, location="contacts") is True
        assert fake.releases["acme/packs"]["id"] == release_id
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 2
        assert fake.releases_yml_writes[rp] == writes_after_first + 1
        content = fake.releases_yml[rp].decode()
        tarball = fake.releases["acme/packs"]["assets"]["crm.artifact.tar.gz"][1]
        expected_digest = "sha256:" + hashlib.sha256(tarball).hexdigest()
        assert f"digest: {expected_digest}" in content


def test_missing_release_catalog_is_repaired_on_redeploy(monkeypatch):
    """Release+asset already correct + releases.yml missing → the deploy
    must repair the catalog: 'unchanged artifact' refers to the release and
    asset, not to the release catalog. A missing/stale catalog is written."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)
        rp = "contacts/.yak/releases.yml"

        repo = GithubReleaseRepository("acme/packs")
        # First deploy creates the release + asset, but simulate that the
        # release-catalog write failed or never happened (catalog absent).
        assert repo.deploy("crm", store, location="contacts") is True
        release_id = fake.releases["acme/packs"]["id"]
        assert fake.releases_yml_writes[rp] == 1

        # Drop the release catalog as if it had never been written.
        fake.releases_yml.pop(rp, None)
        fake.releases_yml_sha.pop(rp, None)

        # Redeploy of the unchanged build: the release + asset are a no-op,
        # but the missing catalog is repaired (written once, then stable).
        assert repo.deploy("crm", store, location="contacts") is True
        assert fake.releases["acme/packs"]["id"] == release_id
        assert fake.uploaded_assets.count("crm.artifact.tar.gz") == 1
        repair_writes = fake.releases_yml_writes[rp]
        assert repair_writes == 2  # first write + repair write

        # Once repaired, the next redeploy is a full no-op — no write.
        assert repo.deploy("crm", store, location="contacts") is True
        assert fake.releases_yml_writes[rp] == repair_writes

        # The repaired catalog reflects the exact published artifact.
        content = fake.releases_yml[rp].decode()
        tarball = fake.releases["acme/packs"]["assets"]["crm.artifact.tar.gz"][1]
        expected_digest = "sha256:" + hashlib.sha256(tarball).hexdigest()
        assert f"digest: {expected_digest}" in content


def test_deploy_preserves_release_history(monkeypatch):
    """A second version adds a release; the first is never overwritten."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        repo = GithubReleaseRepository("acme/packs")
        rp = "contacts/.yak/releases.yml"

        v1 = _published(home, "crm", "1.0.0", mount="/opt/contacts")
        assert repo.deploy("crm", v1, location="contacts") is True

        v2 = _published(home, "crm", "1.1.0", mount="/opt/contacts")
        assert repo.deploy("crm", v2, location="contacts") is True

        content = fake.releases_yml[rp].decode()
        assert "1.0.0:" in content
        assert "1.1.0:" in content
        assert "tag: crm-v1.0.0" in content
        assert "tag: crm-v1.1.0" in content


def test_deploy_owns_each_components_release_catalog(monkeypatch):
    """Two components in one repository own independent release catalogs:
    deploying runtime-engine never touches runtime-store."""
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        repo = GithubReleaseRepository("acme/packs")
        engine_path = "packages/runtime-engine/.yak/releases.yml"
        store_path = "packages/runtime-store/.yak/releases.yml"

        engine = _published(home, "engine", "0.8.0", mount="/opt/engine")
        assert repo.deploy("engine", engine, location="packages/runtime-engine") is True
        assert engine_path in fake.releases_yml
        assert store_path not in fake.releases_yml

        store = _published(home, "runtime-store", "0.5.0", mount="/opt/store")
        assert (
            repo.deploy("runtime-store", store, location="packages/runtime-store")
            is True
        )
        assert store_path in fake.releases_yml

        # engine's catalog is byte-identical to before the store deploy.
        engine_content = fake.releases_yml[engine_path].decode()
        assert "tag: engine-v0.8.0" in engine_content
        assert "runtime-store" not in engine_content


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


def _args(**kw) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


def test_deploy_requires_to_for_a_local_component(monkeypatch):
    """A local-source component distributes locally — --to is required."""
    from y5n.apps.yak.hosts.cli.commands import deploy as deploy_cmd
    from y5n.apps.yak.hosts.cli.cwd import Context
    from y5n.apps.yak.installation.manager import InstallationManager
    from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
    from y5n.apps.yak.repository.file_repo import FileRepository

    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        deploy_cmd,
        "deploy_artifact",
        lambda name, target, location: calls.append((name, target, location)) or True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        make_source(repo, {"cool-shell": "cool-shell"})
        ctx = Context(path=root, sources=[str(repo)])
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )

        deploy_cmd.run(_args(name="cool-shell", to=None), mgr)
        assert calls == []  # local default is refused, not guessed

        deploy_cmd.run(_args(name="cool-shell", to="github:acme/shell-repo"), mgr)
        assert calls == [("cool-shell", "github:acme/shell-repo", "cool-shell")]
