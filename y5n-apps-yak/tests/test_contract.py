"""The minimal Yak contract — source vs artifact, one lifecycle (ADR-21).

Reference tests for the core model:

1. A component in a ``--path`` catalog resolves ``location`` → a source.
2. Everything else resolves ``release`` → an artifact.
3. Source and artifact produce the same structure result — and a
   component without ``structure/`` produces no structure at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_source, source_pack
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _mgr(root: Path, sources: list[str]) -> InstallationManager:
    ctx = Context(path=root, sources=sources)
    return InstallationManager(FileRepository(), DirectoryArtifactStore(), context=ctx)


def _structure(inst: Path, name: str) -> Path:
    return inst / ".yak" / "components" / name / "structure"


def test_path_catalog_resolves_source(tmp_path):
    """A component in a --path catalog uses ``location`` → a local source."""
    src = tmp_path / "src"
    source_pack(src / "acme-widget", "acme-widget", "/opt/acme")
    make_source(src, {"acme-widget": {"location": "acme-widget"}})

    mgr = _mgr(tmp_path, [])
    inst = mgr.install(tmp_path / "inst", identity="acme-widget", paths=[str(src)])

    assert inst is not None
    record = next(c for c in inst.components if c.name == "acme-widget")
    assert record.mode == "source"
    assert record.source == str(src / "acme-widget")
    # The structure is staged (symlinked) into the component store.
    assert _structure(inst.root, "acme-widget").is_symlink()


def test_install_resolves_release_artifact(tmp_path):
    """install uses ``release`` → a published artifact."""
    src = tmp_path / "src"
    source_pack(src / "acme-widget", "acme-widget", "/opt/acme")
    make_source(
        src,
        {
            "acme-widget": {
                "location": "acme-widget",
                "release": "acme-widget",
            }
        },
    )

    mgr = _mgr(tmp_path, [str(src)])
    inst = mgr.install(tmp_path / "inst", identity="acme-widget")

    assert inst is not None
    record = next(c for c in inst.components if c.name == "acme-widget")
    assert record.mode == "artifact"
    # Artifact is copied (self-contained), not symlinked.
    assert _structure(inst.root, "acme-widget").is_dir()
    assert not _structure(inst.root, "acme-widget").is_symlink()


def test_source_and_artifact_same_structure_result(tmp_path):
    """source and artifact materialize the same structure; none without it."""
    src = tmp_path / "src"
    source_pack(src / "acme-widget", "acme-widget", "/opt/acme")
    make_source(
        src,
        {
            "acme-widget": {
                "location": "acme-widget",
                "release": "acme-widget",
            }
        },
    )

    # Source mode (via --path).
    mgr_src = _mgr(tmp_path, [str(src)])
    inst_src = mgr_src.install(
        tmp_path / "inst-src", identity="acme-widget", paths=[str(src)]
    )
    assert inst_src is not None
    src_struct = _structure(inst_src.root, "acme-widget")
    assert src_struct.exists()
    assert src_struct.is_symlink()
    assert (src_struct / "payload.txt").read_text() == "acme-widget-source"

    # Artifact mode (via release).
    mgr_art = _mgr(tmp_path, [str(src)])
    inst_art = mgr_art.install(tmp_path / "inst-art", identity="acme-widget")
    assert inst_art is not None
    art_struct = _structure(inst_art.root, "acme-widget")
    assert art_struct.exists()
    assert not art_struct.is_symlink()
    assert (art_struct / "payload.txt").read_text() == "acme-widget-source"


def test_source_without_structure_produces_none(tmp_path):
    """A pure Python source without ``structure/`` stages nothing."""
    src = tmp_path / "src"
    (src / "acme-lib").mkdir(parents=True)
    (src / "acme-lib" / "pyproject.toml").write_text("[project]\nname = 'acme-lib'\n")
    make_source(src, {"acme-lib": {"location": "acme-lib"}})

    mgr = _mgr(tmp_path, [])
    inst = mgr.install(tmp_path / "inst", identity="acme-lib", paths=[str(src)])

    assert inst is not None
    record = next(c for c in inst.components if c.name == "acme-lib")
    assert record.mode == "source"
    assert not _structure(inst.root, "acme-lib").exists()


def test_install_without_release_is_an_error(tmp_path):
    """install in artifact mode without a release fails clearly — no fallback."""
    src = tmp_path / "src"
    source_pack(src / "acme-widget", "acme-widget", "/opt/acme")
    make_source(src, {"acme-widget": {"location": "acme-widget"}})

    mgr = _mgr(tmp_path, [str(src)])
    with pytest.raises(Exception, match="no release"):
        mgr.install(tmp_path / "inst", identity="acme-widget")
