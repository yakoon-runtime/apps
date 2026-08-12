"""Language-neutrality proof: a non-Python artifact (no wheel, no pip).

A fake ".NET" component flows through the whole lifecycle: resolve → add
→ .yak/components/<name>/structure → materialize → tree node →
publish → deploy → resolve → add-again. The payload is never installed
into a Python venv; only the namespace is materialized.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.publisher.publish import deploy_artifact, publish_local
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.resolver.github import GithubReleaseRepository


def _dotnet_artifact(staging: Path) -> Path:
    store = staging / "acme-test-1.0.0.dotnet.artifact"
    (store / "structure" / ".yak").mkdir(parents=True)
    (store / "structure" / ".yak" / "yak.yml").write_text(
        "title: Acme\n"
        "resolvable: false\n"
        "navigable: true\n"
        "contextual: false\n"
        "expose: true\n"
    )
    (store / "structure" / "hello" / ".yak").mkdir(parents=True)
    (store / "structure" / "hello" / ".yak" / "yak.yml").write_text(
        "title: Acme Hello\n"
        "resolvable: true\n"
        "navigable: false\n"
        "contextual: false\n"
        "host: /boot/dotnet/runtime\n"
        "entry:\n"
        "  run: acme.hello:main\n"
    )
    (store / "payload").mkdir()
    (store / "payload" / "acme-test").write_text("#!/bin/sh\necho hello\n")
    (store / "artifact.yml").write_text(
        "name: acme-test\n"
        "version: 1.0.0\n"
        "kind: package\n"
        "builder: dotnet\n"
        "host: dotnet\n"
        "mount: /opt/acme\n"
        "fingerprint: sha256:xyz\n"
    )
    return store


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
    def __init__(self) -> None:
        self.releases: dict[str, dict] = {}

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
            return _FakeResp(b"{}")

        if "/dl/" in full:
            name = full.rsplit("/", 1)[1]
            for release in self.releases.values():
                if name in release["assets"]:
                    return _FakeResp(release["assets"][name])
            raise OSError("asset not found")

        raise AssertionError(f"unexpected request: {full}")


def _tree_resolves(structure: Path) -> bool:
    import asyncio

    from y5n.runtime.engine.executor import (
        ExecutorKind,
        ExecutorRegistry,
        RuntimeExecutor,
    )
    from y5n.runtime.engine.nodes.tree import Tree

    async def run() -> bool:
        registry = ExecutorRegistry()
        registry.register(ExecutorKind.RUNTIME, RuntimeExecutor())
        tree = Tree(root_path=structure, executors=registry)
        tree.build()
        node = tree.find("/opt/acme/hello")
        return node is not None and node.resolvable

    return asyncio.run(run())


def test_non_python_component_lifecycle(monkeypatch):
    fake = FakeGithub()
    monkeypatch.setattr("y5n.apps.yak.resolver.github.urlopen", fake.urlopen)
    monkeypatch.setattr("y5n.apps.yak.resolver.github.Request", _FakeRequest)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

        ctx = root / "ctx"
        (ctx / ".yak" / "artifacts").mkdir(parents=True)
        (ctx / ".yak" / "context.toml").write_text("[context]\nname = 'ctx'\n")
        _dotnet_artifact(ctx / ".yak" / "artifacts")
        monkeypatch.chdir(ctx)

        # Real platform namespaces (root with .yak/path) so the workspace
        # tree has a root.
        repo_root = Path(__file__).resolve().parents[3]

        mgr = InstallationManager(
            FileRepository(),
            DirectoryArtifactStore(ctx / ".yak" / "artifacts"),
            packs_root=repo_root / "packs",
            runtime_root=repo_root / "runtime",
        )
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("acme-test", inst)

        # Namespace is staged and materialized — no wheel involved.
        staged = inst / ".yak" / "components" / "acme-test" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        assert (staged / "hello" / ".yak" / "yak.yml").exists()

        ws = inst / "structure" / "opt" / "acme"
        assert ws.is_symlink()
        assert (ws / "hello").exists()

        state = mgr.load(inst)
        assert state is not None
        record = next(c for c in state.components if c.name == "acme-test")
        assert record.mode == "artifact"
        assert record.package == ""

        # Node is reachable in the workspace tree (namespace side).
        assert _tree_resolves(inst / "structure")

        # publish: context staging → global store (neutral transport).
        published = publish_local("acme-test")
        assert published is not None
        assert published.parent == home / ".yak" / "artifacts"
        assert (published / "structure" / "hello").exists()

        # deploy → resolve: same namespace + fingerprint, no Python.
        assert deploy_artifact("acme-test", "github:acme/packs") is True
        repo = GithubReleaseRepository("acme/packs")
        artifact = repo.resolve("acme-test")
        assert artifact is not None
        assert artifact.path is not None
        assert artifact.fingerprint == "xyz"
        assert (artifact.path / "structure" / "hello").exists()

        # A second installation resolves the same component from the repo.
        mgr2 = InstallationManager(
            FileRepository(),
            DirectoryArtifactStore(ctx / ".yak" / "artifacts"),
        )
        inst2 = root / "inst2"
        mgr2.install(inst2)
        mgr2.add(
            "acme-test",
            inst2,
            sources=["github:acme/packs"],
            sources_exclusive=True,
        )
        staged2 = inst2 / ".yak" / "components" / "acme-test" / "structure"
        assert (staged2 / "hello" / ".yak" / "yak.yml").exists()
