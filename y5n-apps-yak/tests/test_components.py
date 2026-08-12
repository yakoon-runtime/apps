"""M1 acceptance: components live in .yak/components/ (the install boundary).

Invariant: the workspace materializes exclusively from staged component
paths (``.yak/components/<name>/structure``) — never from artifact stores
or language packages. Source components are symlinked, artifact
components are copied (self-contained).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.environment.io import load as load_env
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.pack.models import Mount, PackName
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.workspace.materializer import Materializer


def _platform_mgr(root: Path, *, with_system: bool = True) -> InstallationManager:
    """A manager with source packs, root and boot platform components."""
    repos = root / "repos"
    if with_system:
        (repos / "y5n-packs-system" / "structure" / "bin").mkdir(parents=True)
        (repos / "y5n-packs-system" / "structure" / "bin" / "ls").write_text(
            "echo hi\n"
        )
        (repos / "y5n-packs-system" / "pack.toml").write_text(
            'name = "system"\nversion = "0.1"\nmount = "/usr/bin"\n'
        )
    packs_root = root / "packs"
    runtime_root = root / "runtime"
    (packs_root / "y5n-packs-root" / "structure" / ".yak").mkdir(parents=True)
    (packs_root / "y5n-packs-root" / "structure" / "usr").mkdir(parents=True)
    (runtime_root / "y5n-runtime-boot" / "structure" / "python").mkdir(parents=True)
    return InstallationManager(
        FileRepository(repos),
        DirectoryArtifactStore(repos),
        packs_root=packs_root,
        runtime_root=runtime_root,
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


def test_install_stages_platform_components():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root)
        inst = root / "inst"
        mgr.install(inst)

        for name in ("root", "boot"):
            staged = inst / ".yak" / "components" / name / "structure"
            assert staged.is_symlink()

        env = load_env(inst)
        assert env is not None
        assert env.components == [PackName("root"), PackName("boot")]
        assert all(
            m.source.startswith(str(inst / ".yak" / "components")) for m in env.mounts
        )

        state = mgr.load(inst)
        assert state is not None
        assert [c.name for c in state.components] == ["root", "boot"]


def test_add_source_pack_is_source_linked():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("system", inst)

        staged = inst / ".yak" / "components" / "system" / "structure"
        assert staged.is_symlink()
        assert (
            staged.resolve()
            == (root / "repos" / "y5n-packs-system" / "structure").resolve()
        )

        env = load_env(inst)
        assert env is not None
        sys_mount = next(m for m in env.mounts if m.target == "/usr/bin")
        assert Path(sys_mount.source) == staged

        # The workspace symlink points at the staged component path, not the source.
        ws = inst / "structure" / "usr" / "bin"
        assert ws.is_symlink()
        assert ws.readlink() == staged

        # Platform mounts survive the add (no pruning of staged mounts).
        assert (inst / "structure" / "boot").is_symlink()
        assert (inst / "structure" / ".yak").is_symlink()

        state = mgr.load(inst)
        assert state is not None
        record = next(c for c in state.components if c.name == "system")
        assert record.mode == "source"
        assert record.source == str(root / "repos" / "y5n-packs-system" / "structure")


def test_workspace_points_at_component_store_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("system", inst)

        prefix = str(inst / ".yak" / "components")
        for entry in (inst / "structure").rglob("*"):
            if entry.is_symlink():
                assert str(entry.readlink()).startswith(prefix), entry


def test_artifact_component_survives_store_deletion(monkeypatch):
    monkeypatch.setattr(
        "y5n.apps.yak.resolver.install.install_artifact", lambda *a, **k: True
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "erp", "1.0.0", "sha256:abc", "content")

        mgr = _platform_mgr(root, with_system=False)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("erp", inst)

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        assert (staged / "payload.txt").read_text() == "content"

        # GOLD: removing the global artifact store must not break the component.
        shutil.rmtree(home / ".yak")

        assert (staged / "payload.txt").read_text() == "content"
        ws = inst / "structure" / "opt" / "erp"
        assert ws.is_symlink()
        assert (ws / "payload.txt").read_text() == "content"

        issues = mgr.doctor(inst)
        assert any("erp" in i and "✓" in i for i in issues)


def test_doctor_detects_dangling_source_component():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("system", inst)

        shutil.rmtree(root / "repos" / "y5n-packs-system" / "structure")

        issues = mgr.doctor(inst)
        assert any("dangling" in i for i in issues)


def test_update_artifact_refreshes_component(monkeypatch):
    monkeypatch.setattr(
        "y5n.apps.yak.resolver.install.install_artifact", lambda *a, **k: True
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "erp", "1.0.0", "sha256:old", "v1")

        mgr = _platform_mgr(root, with_system=False)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("erp", inst)

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert (staged / "payload.txt").read_text() == "v1"

        # The store now holds v2.
        shutil.rmtree(home / ".yak" / "artifacts" / "erp-1.0.0.python.artifact")
        _write_artifact(home, "erp", "2.0.0", "sha256:new", "v2")

        mgr.update(inst)

        # Same canonical path, refreshed content + identity.
        assert staged.exists()
        assert (staged / "payload.txt").read_text() == "v2"
        state = mgr.load(inst)
        assert state is not None
        record = next(c for c in state.components if c.name == "erp")
        assert record.version == "2.0.0"
        assert record.fingerprint == "new"
        assert record.mount == "/opt/erp"


def test_materializer_refuses_store_source():
    mat = Materializer()
    store = Path.home() / ".yak" / "artifacts" / "x" / "structure"
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError, match="Refusing"):
            mat.materialize(
                Path(tmp) / "structure",
                mounts=[Mount(source=str(store), target="/opt")],
            )


def test_materializer_prunes_removed_component():
    mat = Materializer()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        comps = root / ".yak" / "components"
        (comps / "gone" / "structure").mkdir(parents=True)
        (comps / "keep" / "structure").mkdir(parents=True)

        structure_dir = root / "structure"
        structure_dir.mkdir(parents=True)
        (structure_dir / "gone").symlink_to(comps / "gone" / "structure", True)
        (structure_dir / "keep").symlink_to(comps / "keep" / "structure", True)

        mounts = [Mount(source=str(comps / "keep" / "structure"), target="/keep")]
        mat.materialize(structure_dir, mounts=mounts, components_dir=comps)

        assert not (structure_dir / "gone").exists()
        assert (structure_dir / "keep").is_symlink()
