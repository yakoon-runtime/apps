"""ADR-20 gold test: Yak materializes the components the bootstrap declares.

Yak knows no component names. A source catalog provides component
locations; the Context's ``install`` list names what to install. Both
``install`` and a reconciled ``update`` converge to the declared set —
with no installer change, because the desired set is fully declarative.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

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
    components = {name: {"location": f"artifacts/{name}-art"} for name in names}
    for name in names:
        make_artifact(repo / "artifacts" / f"{name}-art", name, f"/opt/{name}")
    make_source(repo, components)
    return repo


def _mgr(root: Path, repo: Path, install: list[str]) -> InstallationManager:
    ctx = Context(path=root, sources=[str(repo)], install=install)
    return InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=ctx,
    )


def test_install_materializes_declared_components():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _build_repo(root, ["foo", "bar", "baz"])
        mgr = _mgr(root, repo, ["foo", "bar", "baz"])
        inst = mgr.install(root / "inst")

        state = mgr.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["bar", "baz", "foo"]
        assert all(c.mode == "artifact" for c in state.components)
        for name in ("foo", "bar", "baz"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir() and not staged.is_symlink()

        env = load_env(inst.root)
        assert env is not None
        assert sorted(str(c) for c in env.components) == ["bar", "baz", "foo"]


def test_update_converges_to_changed_desired_set():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _build_repo(root, ["foo", "bar", "baz"])
        mgr = _mgr(root, repo, ["foo", "bar", "baz"])
        inst = mgr.install(root / "inst")

        # The desired set changes to foo + quux: the source grows quux,
        # and the materialized SOLL is edited accordingly.
        make_artifact(repo / "artifacts" / "quux-art", "quux", "/opt/quux")
        make_source(
            repo,
            {
                "foo": {"location": "artifacts/foo-art"},
                "quux": {"location": "artifacts/quux-art"},
            },
        )
        touch(inst.root, name="fake", components=["foo", "quux"])

        mgr2 = _mgr(root, repo, ["foo", "quux"])
        mgr2.update(inst.root)

        state = mgr2.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["foo", "quux"]
        for name in ("foo", "quux"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir()
        for name in ("bar", "baz"):
            assert not (inst.root / ".yak" / "components" / name).exists()
