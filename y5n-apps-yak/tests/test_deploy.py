"""M2 acceptance: deploy makes a published artifact available remotely.

Contract:

    yak deploy <component> --to <repository>
        precondition:  component is published locally (~/.yak/artifacts/)
        postcondition: repository.resolve(component) can retrieve it

GitHub is mocked at the HTTP layer.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.publisher.publish import deploy_artifact
from y5n.apps.yak.resolver.github import GithubReleaseRepository
from y5n.apps.yak.resolver.install import expand_repository_specs, repository_for


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

    def urlopen(self, url):
        full = url.full_url if hasattr(url, "full_url") else str(url)
        method = getattr(url, "method", "GET")
        data = getattr(url, "data", None)

        if "/releases/latest" in full:
            repo = full.split("/repos/", 1)[1].split("/releases", 1)[0]
            release = self.releases.get(repo)
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

        if full.endswith("/releases") and method == "POST":
            repo = full.split("/repos/", 1)[1].split("/releases", 1)[0]
            body = json.loads((data or b"").decode())
            assert body["draft"] is False, "deploy must publish, not draft"
            self.releases[repo] = {"tag": body["tag_name"], "assets": {}}
            upload_url = f"https://uploads.gh/repos/{repo}/releases/1/assets"
            return _FakeResp(
                json.dumps(
                    {"id": 1, "upload_url": upload_url + "{?name,label}"}
                ).encode()
            )

        if "/assets" in full and method == "POST":
            repo = full.split("/repos/", 1)[1].split("/releases/", 1)[0]
            name = full.split("name=", 1)[1]
            self.releases[repo]["assets"][name] = data
            self.uploaded_assets.append(name)
            return _FakeResp(b"{}")

        if "/dl/" in full:
            name = full.rsplit("/", 1)[1]
            for release in self.releases.values():
                if name in release["assets"]:
                    return _FakeResp(release["assets"][name])
            raise OSError("asset not found")

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
        "mount: /opt/crm\n"
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
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    return fake


def test_deploy_then_resolve_roundtrip(monkeypatch):
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)

        repo = GithubReleaseRepository("acme/packs")
        assert repo.deploy("crm", store) is True
        assert fake.uploaded_assets == ["crm.artifact.tar.gz"]

        artifact = repo.resolve("crm")
        assert artifact is not None
        assert artifact.path is not None
        assert artifact.fingerprint == "abc123"
        assert artifact.version == "1.0.0"
        assert (artifact.path / "structure" / "x.txt").read_text() == "data"


def test_deploy_is_not_draft(monkeypatch):
    fake = _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        store = _published_artifact(home)
        GithubReleaseRepository("acme/packs").deploy("crm", store)
        assert fake.releases["acme/packs"]["tag"] == "crm-v1.0.0"


def test_deploy_artifact_requires_published(monkeypatch):
    _mock_github(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        home = _mock_home(monkeypatch, tmp)
        result = deploy_artifact("crm", "acme/packs")
        assert result is None


def test_repository_for_named_from_context(monkeypatch):
    ctx = Context(
        path=Path("/tmp/x"),
        named_repositories={"acme": {"type": "github", "repo": "acme/packs"}},
    )
    monkeypatch.setattr(
        "y5n.apps.yak.hosts.cli.cwd.Context.current", staticmethod(lambda: ctx)
    )
    repo = repository_for("acme")
    assert repo is not None
    assert repo._repo == "acme/packs"

    inline = repository_for("github:other/repo")
    assert inline is not None
    assert inline._repo == "other/repo"


def test_expand_repository_specs(monkeypatch):
    ctx = Context(
        path=Path("/tmp/x"),
        named_repositories={"acme": {"type": "github", "repo": "acme/packs"}},
    )
    monkeypatch.setattr(
        "y5n.apps.yak.hosts.cli.cwd.Context.current", staticmethod(lambda: ctx)
    )
    assert expand_repository_specs(["acme", "github:other/repo"]) == [
        "github:acme/packs",
        "github:other/repo",
    ]
