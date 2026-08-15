"""Installer invariants: healing, replacement, orphans, exclusivity."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from conftest import artifact as make_artifact
from conftest import make_source, source_pack
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _platform_mgr(
    root: Path, monkeypatch, *, extra_components: dict | None = None
) -> InstallationManager:
    repo = root / "repo"
    components: dict = {
        "acme-system": {"location": "packs/acme-system"},
        "acme-root": {"location": "packs/acme-root"},
        "acme-boot": {"location": "runtime/acme-boot"},
    }
    source_pack(repo / "packs" / "acme-system", "acme-system", "/usr/bin")
    source_pack(repo / "packs" / "acme-root", "acme-root", "/")
    source_pack(repo / "runtime" / "acme-boot", "acme-boot", "/boot")
    components.update(extra_components or {})
    make_source(
        repo,
        components,
        bundles={"platform": ["acme-root", "acme-boot"]},
    )
    ctx = Context(path=root, sources=[str(repo)])
    return InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=ctx,
    )


def _platform(mgr: InstallationManager, inst: Path) -> None:
    repo = inst.parent / "repo"
    mgr.install(inst, identity="platform", paths=[str(repo)])


def _erp_source(root: Path, content: str = "data") -> Path:
    repo = root / "repo"
    make_artifact(repo / "artifacts" / "erp-art", "erp", "/opt/erp", content)
    make_source(
        repo,
        {
            "erp": {
                "location": "artifacts/erp-art",
                "release": "artifacts/erp-art",
            }
        },
    )
    return repo


@pytest.mark.slow
def test_update_heals_deleted_artifact_structure(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _erp_source(root)
        ctx = Context(path=root, sources=[str(repo)])
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        inst = root / "inst"
        mgr.install(inst, identity="erp")

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert (staged / "payload.txt").read_text() == "data"

        shutil.rmtree(inst / ".yak" / "components" / "erp")
        assert not staged.exists()

        mgr.update(inst)
        assert (staged / "payload.txt").read_text() == "data"


@pytest.mark.slow
def test_update_heals_deleted_platform_component(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        _platform(mgr, inst)

        boot = inst / ".yak" / "components" / "acme-boot"
        assert boot.exists()
        shutil.rmtree(boot)

        mgr.update(inst)
        assert (inst / ".yak" / "components" / "acme-boot" / "structure").exists()


@pytest.mark.slow
def test_mode_switch_replaces_component(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        official = root / "official"
        make_artifact(official / "erp-art", "erp", "/opt/erp", "data")
        make_source(
            official,
            {"erp": {"location": "erp-art", "release": "erp-art"}},
        )
        ctx_art = Context(path=root, sources=[str(official)])
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx_art
        )
        inst = root / "inst"
        mgr.install(inst, identity="erp")

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        state = mgr.load(inst)
        assert state is not None
        assert [c.name for c in state.components].count("erp") == 1
        assert next(c for c in state.components if c.name == "erp").mode == "artifact"

        # Re-installing in source mode (via --path) replaces the artifact.
        dev = root / "dev"
        source_pack(dev / "erp", "erp", "/opt/erp")
        make_source(dev, {"erp": {"location": "erp"}})
        ctx_src = Context(path=root, sources=[str(official)])
        mgr2 = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx_src
        )
        mgr2.install(inst, identity="erp", paths=[str(dev)])

        assert staged.is_symlink()
        state = mgr2.load(inst)
        assert state is not None
        assert [c.name for c in state.components].count("erp") == 1
        assert next(c for c in state.components if c.name == "erp").mode == "source"


@pytest.mark.slow
def test_update_removes_orphan_components(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        _platform(mgr, inst)

        orphan = inst / ".yak" / "components" / "stale"
        (orphan / "structure").mkdir(parents=True)

        issues = mgr.doctor(inst)
        assert any("Orphan" in i for i in issues)

        mgr.update(inst)
        assert not orphan.exists()
        issues = mgr.doctor(inst)
        assert not any("Orphan" in i for i in issues)


@pytest.mark.slow
def test_install_rolls_back_partial_staging(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        _platform(mgr, inst)

        def boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(type(mgr._installer), "install", boom)

        with pytest.raises(RuntimeError, match="boom"):
            mgr.install(inst, identity="acme-system", paths=[str(root / "repo")])
        assert not (inst / ".yak" / "components" / "acme-system").exists()


def test_publish_is_local_only():
    import y5n.apps.yak.publisher.publish as publish

    assert not hasattr(publish, "publish_github")
    assert not hasattr(publish, "publish_artifact")
