"""Installer invariants: healing, replacement, orphans, exclusivity."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.pack.models import PackName
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.resolver.install import find_artifact


def _platform_mgr(root: Path, monkeypatch) -> InstallationManager:
    home = root / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    repos = root / "repos"
    (repos / "y5n-packs-system" / "structure").mkdir(parents=True)
    (repos / "y5n-packs-system" / "pack.toml").write_text(
        'name = "y5n-packs-system"\nversion = "0.1"\nmount = "/usr/bin"\n'
    )
    packs_root = root / "packs"
    runtime_root = root / "runtime"
    (packs_root / "y5n-packs-root" / "structure" / ".yak").mkdir(parents=True)
    (packs_root / "y5n-packs-root" / "pack.toml").write_text(
        'name = "y5n-packs-root"\nversion = "0.1"\nmount = "/"\n'
    )
    (runtime_root / "y5n-runtime-boot" / "structure" / "python").mkdir(parents=True)
    (runtime_root / "y5n-runtime-boot" / "pack.toml").write_text(
        'name = "y5n-runtime-boot"\nversion = "0.1"\nmount = "/boot"\n'
    )
    env_dir = home / ".yak" / "artifacts" / "environments"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "test.yml").write_text(
        "name: test\ncomponents:\n  - y5n-packs-root\n  - y5n-runtime-boot\n"
    )
    ctx = Context(
        path=root,
        environment="test",
        component_sources={
            "y5n-packs-root": str(packs_root / "y5n-packs-root"),
            "y5n-runtime-boot": str(runtime_root / "y5n-runtime-boot"),
        },
    )
    return InstallationManager(
        FileRepository(repos),
        DirectoryArtifactStore(repos),
        context=ctx,
    )


def _write_artifact(
    home: Path, name: str, version: str, fingerprint: str, content: str
) -> Path:
    store = home / ".yak" / "artifacts" / f"{name}-{version}.python.artifact"
    (store / "structure").mkdir(parents=True)
    (store / "structure" / "payload.txt").write_text(content)
    (store / "artifact.yml").write_text(
        "name: " + name + "\n"
        "version: " + version + "\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        "mount: /opt/erp\n"
        "fingerprint: " + fingerprint + "\n"
    )
    return store


def test_update_heals_deleted_artifact_structure(monkeypatch):
    monkeypatch.setattr(
        "y5n.apps.yak.resolver.install.install_artifact", lambda *a, **k: True
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "erp", "1.0.0", "sha256:abc", "data")

        mgr = _platform_mgr(root, monkeypatch)
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
    monkeypatch.setattr(
        "y5n.apps.yak.resolver.install.install_artifact", lambda *a, **k: True
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "erp", "1.0.0", "sha256:abc", "data")

        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("erp", inst)

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        state = mgr.load(inst)
        assert state is not None
        assert [c.name for c in state.components].count("erp") == 1
        assert next(c for c in state.components if c.name == "erp").mode == "artifact"

        # A source pack for the same component appears → update switches to source.
        repos = root / "repos"
        (repos / "erp" / "structure").mkdir(parents=True)
        (repos / "erp" / "pack.toml").write_text(
            'name = "erp"\nversion = "0.1"\nmount = "/opt/erp"\n'
        )
        mgr.update(inst)

        assert staged.is_symlink()
        state = mgr.load(inst)
        assert state is not None
        assert [c.name for c in state.components].count("erp") == 1
        assert next(c for c in state.components if c.name == "erp").mode == "source"

        # Source disappears again → update switches back to artifact (copy).
        shutil.rmtree(repos / "erp")
        mgr.update(inst)

        assert staged.is_dir() and not staged.is_symlink()
        state = mgr.load(inst)
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


def test_find_artifact_exclusive_excludes_local_store(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "crm", "1.0.0", "sha256:local", "data")

        assert find_artifact("crm") is not None
        assert find_artifact("crm", sources=[], exclusive=True) is None


def test_publish_is_local_only():
    import y5n.apps.yak.publisher.publish as publish

    assert not hasattr(publish, "publish_github")
    assert not hasattr(publish, "publish_artifact")
