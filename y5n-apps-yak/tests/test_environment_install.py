"""ADR-20 gold test: Yak materializes the components the bundle declares.

Yak knows no component names. A source catalog provides component
locations and releases; a bundle names what to install. ``install``
materializes the bundle's members — with no installer change, because the
desired set is fully declarative.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from conftest import artifact as make_artifact
from conftest import make_source
from y5n.apps.yak.environment.io import load as load_env
from y5n.apps.yak.environment.io import touch
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _build_repo(root: Path, names: list[str]) -> Path:
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
    make_source(repo, components, bundles={"all": names})
    return repo


def _mgr(root: Path, repo: Path) -> InstallationManager:
    ctx = Context(path=root, sources=[str(repo)])
    return InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=ctx,
    )


@pytest.mark.slow
def test_install_materializes_bundle_members():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _build_repo(root, ["foo", "bar", "baz"])
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst", identity="all")

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["bar", "baz", "foo"]
        assert all(c.mode == "artifact" for c in state.components)
        for name in ("foo", "bar", "baz"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir() and not staged.is_symlink()

        env = load_env(inst.root)
        assert env is not None
        assert env.install == {"all": []}


@pytest.mark.slow
def test_update_converges_to_bundle_growth_and_shrink():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _build_repo(root, ["foo", "bar", "baz"])
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst", identity="all")
        assert inst is not None
        env = load_env(inst.root)
        assert env is not None
        assert env.install == {"all": []}

        # The catalog bundle grows quux and shrinks bar+baz. ``update``
        # re-resolves the identity against the current bundle, so the
        # environment converges: quux is added, bar/baz disappear.
        make_artifact(repo / "artifacts" / "quux-art", "quux", "/opt/quux")
        make_source(
            repo,
            {
                "foo": {
                    "location": "artifacts/foo-art",
                    "release": "artifacts/foo-art",
                },
                "quux": {
                    "location": "artifacts/quux-art",
                    "release": "artifacts/quux-art",
                },
            },
            bundles={"all": ["foo", "quux"]},
        )

        mgr2 = _mgr(root, repo)
        mgr2.update(inst.root)

        state = mgr2.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["foo", "quux"]
        for name in ("foo", "quux"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir()
        for name in ("bar", "baz"):
            assert not (inst.root / ".yak" / "components" / name).exists()
