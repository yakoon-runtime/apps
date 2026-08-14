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
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


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
    """A minimal GitHub Releases API: releases hold named assets."""

    def __init__(self) -> None:
        self.releases: dict[str, dict] = {}
        self.uploaded_assets: list[str] = []
        self._next_id = 1

    def _release(self, repo: str) -> dict | None:
        return self.releases.get(repo)

    def _upload_url(self, repo: str, rid: int) -> str:
        return f"https://uploads.gh/repos/{repo}/releases/{rid}/assets"

    def urlopen(self, url):
        full = url.full_url if hasattr(url, "full_url") else str(url)
        method = getattr(url, "method", "GET")
        data = getattr(url, "data", None)

        if "/releases?" in full:
            repo = full.split("/repos/", 1)[1].split("/releases", 1)[0]
            release = self._release(repo)
            releases = []
            if release is not None:
                assets = [
                    {
                        "name": name,
                        "browser_download_url": (
                            f"https://gh/{repo}/dl/{release['tag']}/{name}"
                        ),
                    }
                    for name in release["assets"]
                ]
                releases.append({"tag_name": release["tag"], "assets": assets})
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
            assets = [
                {"id": aid, "name": name}
                for name, (aid, _bytes) in release["assets"].items()
            ]
            return _FakeResp(json.dumps(assets).encode())

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


@pytest.mark.slow
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
        monkeypatch.chdir(ctx)

        # A source catalog: the real platform namespaces (so the workspace
        # tree has a root) plus the language-neutral artifact.
        repo_root = Path(__file__).resolve().parents[3]
        source = root / "repo"
        (source / "packs").mkdir(parents=True)
        (source / "runtime").mkdir(parents=True)
        (source / "packs" / "y5n-packs-root").symlink_to(
            repo_root / "packs" / "y5n-packs-root", target_is_directory=True
        )
        (source / "runtime" / "y5n-runtime-boot").symlink_to(
            repo_root / "runtime" / "y5n-runtime-boot", target_is_directory=True
        )
        _dotnet_artifact(source)
        from conftest import make_source

        make_source(
            source,
            {
                "y5n-packs-root": {"location": "packs/y5n-packs-root"},
                "y5n-runtime-boot": {"location": "runtime/y5n-runtime-boot"},
                "acme-test": {"location": "acme-test-1.0.0.dotnet.artifact"},
            },
        )
        ctx_obj = Context(
            path=ctx,
            sources=[str(source)],
            install=["y5n-packs-root", "y5n-runtime-boot"],
        )

        mgr = InstallationManager(
            FileRepository(),
            DirectoryArtifactStore(),
            context=ctx_obj,
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
