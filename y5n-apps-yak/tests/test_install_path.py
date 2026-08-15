"""install --path (ADR-21) — preferred local catalogs, per-component mode.

A component found in any ``--path`` catalog resolves through its
``location`` (source); everything else resolves through its ``release``
(artifact) — per component, no global mode. Real cases: all release, all
source, and mixed, plus a repeatable ``--path`` that shadows a release.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from conftest import artifact as make_artifact
from conftest import make_source, source_pack
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _release_dir(root: Path, dirname: str, names: list[str], bundles=None) -> Path:
    repo = root / dirname
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


def _source_dir(root: Path, dirname: str, names: list[str], bundles=None) -> Path:
    repo = root / dirname
    components = {name: {"location": f"packs/{name}"} for name in names}
    for name in names:
        source_pack(repo / "packs" / name, name, f"/opt/{name}")
    make_source(repo, components, bundles=bundles)
    return repo


def _mgr(root: Path, sources: list[Path]) -> InstallationManager:
    ctx = Context(path=root, sources=[str(s) for s in sources])
    return InstallationManager(
        FileRepository(), DirectoryArtifactStore(), context=ctx
    )


def _structure(inst: Path, name: str) -> Path:
    return inst / ".yak" / "components" / name / "structure"


@pytest.mark.slow
def test_all_release_without_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = _release_dir(
            root, "remote", ["widget", "erp"], bundles={"runtime": ["widget", "erp"]}
        )
        mgr = _mgr(root, [remote])
        inst = mgr.install(root / "inst", identity="runtime")

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        assert all(c.mode == "artifact" for c in state.components)
        for name in ("widget", "erp"):
            assert _structure(inst.root, name).is_dir()
            assert not _structure(inst.root, name).is_symlink()


@pytest.mark.slow
def test_all_source_with_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        local = _source_dir(
            root, "local", ["widget", "erp"], bundles={"runtime": ["widget", "erp"]}
        )
        mgr = _mgr(root, [])
        inst = mgr.install(root / "inst", identity="runtime", paths=[str(local)])

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        assert all(c.mode == "source" for c in state.components)
        for name in ("widget", "erp"):
            assert _structure(inst.root, name).is_symlink()


@pytest.mark.slow
def test_mixed_source_and_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = _release_dir(
            root, "remote", ["widget", "erp"], bundles={"runtime": ["widget", "erp"]}
        )
        local = _source_dir(root, "local", ["widget"])
        mgr = _mgr(root, [remote])
        inst = mgr.install(root / "inst", identity="runtime", paths=[str(local)])

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        by_name = {c.name: c for c in state.components}
        assert by_name["widget"].mode == "source"
        assert by_name["erp"].mode == "artifact"
        assert _structure(inst.root, "widget").is_symlink()
        assert _structure(inst.root, "erp").is_dir()
        assert not _structure(inst.root, "erp").is_symlink()


@pytest.mark.slow
def test_repeatable_path_catalogs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = _release_dir(
            root, "remote", ["widget", "erp"], bundles={"runtime": ["widget", "erp"]}
        )
        local1 = _source_dir(root, "local1", ["widget"])
        local2 = _source_dir(root, "local2", ["erp"])
        mgr = _mgr(root, [remote])
        inst = mgr.install(
            root / "inst",
            identity="runtime",
            paths=[str(local1), str(local2)],
        )

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        by_name = {c.name: c for c in state.components}
        assert by_name["widget"].mode == "source"
        assert by_name["erp"].mode == "source"


@pytest.mark.slow
def test_path_shadows_release():
    """A component in a --path catalog is source even if the index has a release."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = _release_dir(
            root, "remote", ["widget"], bundles={"runtime": ["widget"]}
        )
        local = _source_dir(root, "local", ["widget"])
        mgr = _mgr(root, [remote])
        inst = mgr.install(root / "inst", identity="runtime", paths=[str(local)])

        assert inst is not None
        state = mgr.load(inst.root)
        assert state is not None
        record = next(c for c in state.components if c.name == "widget")
        assert record.mode == "source"
        assert _structure(inst.root, "widget").is_symlink()
