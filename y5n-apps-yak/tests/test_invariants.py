"""Installer invariants: healing, replacement, orphans, exclusivity."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from conftest import artifact as make_artifact
from conftest import environment as make_environment
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
        "y5n-packs-system": {"location": "packs/y5n-packs-system"},
        "y5n-packs-root": {"location": "packs/y5n-packs-root"},
        "y5n-runtime-boot": {"location": "runtime/y5n-runtime-boot"},
    }
    source_pack(repo / "packs" / "y5n-packs-system", "y5n-packs-system", "/usr/bin")
    source_pack(repo / "packs" / "y5n-packs-root", "y5n-packs-root", "/")
    source_pack(repo / "runtime" / "y5n-runtime-boot", "y5n-runtime-boot", "/boot")
    components.update(extra_components or {})
    make_environment(repo, "test", ["y5n-packs-root", "y5n-runtime-boot"])
    make_source(
        repo,
        components,
        environments={"test": "environments/test.yml"},
    )
    ctx = Context(path=root, sources=[str(repo)], environment="test")
    return InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=ctx,
    )


def _erp_source(root: Path, content: str = "data") -> Path:
    repo = root / "repo"
    make_artifact(repo / "artifacts" / "erp-art", "erp", "/opt/erp", content)
    make_environment(repo, "test", [])
    make_source(
        repo,
        {"erp": {"location": "artifacts/erp-art"}},
        environments={"test": "environments/test.yml"},
    )
    return repo


def test_update_heals_deleted_artifact_structure(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _erp_source(root)
        ctx = Context(path=root, sources=[str(repo)], environment="test")
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("erp", inst)

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert (staged / "payload.txt").read_text() == "data"

        shutil.rmtree(inst / ".yak" / "components" / "erp")
        assert not staged.exists()

        mgr.update(inst)
        assert (staged / "payload.txt").read_text() == "data"


def test_update_heals_deleted_platform_component(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)

        boot = inst / ".yak" / "components" / "y5n-runtime-boot"
        assert boot.exists()
        shutil.rmtree(boot)

        mgr.update(inst)
        assert (
            inst / ".yak" / "components" / "y5n-runtime-boot" / "structure"
        ).exists()


def test_mode_switch_replaces_component(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        official = root / "official"
        make_artifact(official / "erp-art", "erp", "/opt/erp", "data")
        make_environment(official, "test", [])
        make_source(
            official,
            {"erp": {"location": "erp-art"}},
            environments={"test": "environments/test.yml"},
        )
        ctx_art = Context(path=root, sources=[str(official)], environment="test")
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx_art
        )
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("erp", inst)

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        state = mgr.load(inst)
        assert state is not None
        assert [c.name for c in state.components].count("erp") == 1
        assert next(c for c in state.components if c.name == "erp").mode == "artifact"

        # A local source for the same component appears first → source wins.
        dev = root / "dev"
        source_pack(dev / "erp", "erp", "/opt/erp")
        make_source(dev, {"erp": {"location": "erp"}})
        ctx_src = Context(
            path=root, sources=[str(dev), str(official)], environment="test"
        )
        mgr2 = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx_src
        )
        mgr2.update(inst)

        assert staged.is_symlink()
        state = mgr2.load(inst)
        assert state is not None
        assert [c.name for c in state.components].count("erp") == 1
        assert next(c for c in state.components if c.name == "erp").mode == "source"

        # The local source disappears again → update switches back to artifact.
        ctx_rel = Context(path=root, sources=[str(official)], environment="test")
        mgr3 = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx_rel
        )
        mgr3.update(inst)

        assert staged.is_dir() and not staged.is_symlink()
        state = mgr3.load(inst)
        assert state is not None
        assert next(c for c in state.components if c.name == "erp").mode == "artifact"


def test_update_removes_orphan_components(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)

        orphan = inst / ".yak" / "components" / "stale"
        (orphan / "structure").mkdir(parents=True)

        issues = mgr.doctor(inst)
        assert any("Orphan" in i for i in issues)

        mgr.update(inst)
        assert not orphan.exists()
        issues = mgr.doctor(inst)
        assert not any("Orphan" in i for i in issues)


def test_add_rolls_back_partial_staging(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)

        def boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(type(mgr._installer), "install", boom)

        with pytest.raises(RuntimeError, match="boom"):
            mgr.add("y5n-packs-system", inst)
        assert not (inst / ".yak" / "components" / "y5n-packs-system").exists()


def test_publish_is_local_only():
    import y5n.apps.yak.publisher.publish as publish

    assert not hasattr(publish, "publish_github")
    assert not hasattr(publish, "publish_artifact")
