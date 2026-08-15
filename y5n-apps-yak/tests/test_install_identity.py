"""install <component|bundle> (ADR-21) — releases only.

The first argument of ``install`` is always an identity: a component or
a bundle name. A bundle resolves to its members through the shared
index; every member resolves through its release. Unknown identities
fail loudly; a member without a release is an error in release-only
mode. On an existing environment the identity's components are added.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from conftest import artifact as make_artifact
from conftest import make_source
from y5n.apps.yak.environment.io import load as load_env
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.resolver.catalog import CatalogError


def _repo(root: Path, names: list[str], bundles: dict | None = None) -> Path:
    repo = root / "repo"
    components = {
        name: {
            "location": f"artifacts/{name}-art",
            "release": f"artifacts/{name}-art",
        }
        for name in names
    }
    for name in names:
        make_artifact(repo / "artifacts" / f"{name}-art", name, f"/opt/{name}")
    make_source(repo, components, bundles=bundles)
    return repo


def _mgr(root: Path, repo: Path) -> InstallationManager:
    ctx = Context(path=root, sources=[str(repo)])
    return InstallationManager(
        FileRepository(), DirectoryArtifactStore(), context=ctx
    )


def _structure(inst: Path, name: str) -> Path:
    return inst / ".yak" / "components" / name / "structure"


@pytest.mark.slow
def test_install_component_resolves_release():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _repo(root, ["foo"])
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst", identity="foo")

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        assert [c.name for c in state.components] == ["foo"]
        record = state.components[0]
        assert record.mode == "artifact"
        assert _structure(inst.root, "foo").is_dir()
        assert not _structure(inst.root, "foo").is_symlink()


@pytest.mark.slow
def test_install_bundle_resolves_all_members():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _repo(root, ["foo", "bar"], bundles={"runtime": ["foo", "bar"]})
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst", identity="runtime")

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["bar", "foo"]
        assert all(c.mode == "artifact" for c in state.components)


@pytest.mark.slow
def test_install_component_on_existing_environment_adds():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _repo(root, ["foo", "bar"])
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst", identity="foo")
        assert inst is not None

        mgr.install(inst.root, identity="bar")

        env = load_env(inst.root)
        assert env is not None
        assert sorted(str(c) for c in env.components) == ["bar", "foo"]
        state = mgr.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["bar", "foo"]


@pytest.mark.slow
def test_install_bundle_on_existing_environment_adds_members():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _repo(
            root,
            ["foo", "bar", "baz"],
            bundles={"runtime": ["bar", "baz"]},
        )
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst", identity="foo")
        assert inst is not None

        mgr.install(inst.root, identity="runtime")

        env = load_env(inst.root)
        assert env is not None
        assert sorted(str(c) for c in env.components) == ["bar", "baz", "foo"]


@pytest.mark.slow
def test_install_unknown_identity_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _repo(root, ["foo"])
        mgr = _mgr(root, repo)
        with pytest.raises(ValueError, match="Unknown identity"):
            mgr.install(root / "inst", identity="nope")


@pytest.mark.slow
def test_install_bundle_member_without_release_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        make_source(
            repo,
            components={
                "foo": {
                    "location": "artifacts/foo-art",
                    "release": "artifacts/foo-art",
                },
                "bar": {"location": "artifacts/bar-art"},
            },
            bundles={"runtime": ["foo", "bar"]},
        )
        make_artifact(repo / "artifacts" / "foo-art", "foo", "/opt/foo")
        make_artifact(repo / "artifacts" / "bar-art", "bar", "/opt/bar")
        mgr = _mgr(root, repo)
        with pytest.raises(CatalogError, match="no release"):
            mgr.install(root / "inst", identity="runtime")
