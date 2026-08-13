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
from conftest import artifact as make_artifact
from conftest import environment as make_environment
from conftest import make_source, source_pack
from y5n.apps.yak.environment.io import load as load_env
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.pack.models import Mount, PackName
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.workspace.materializer import Materializer


def _platform_mgr(
    root: Path,
    monkeypatch,
    *,
    with_system: bool = True,
    extra_components: dict | None = None,
) -> InstallationManager:
    """A manager whose source catalog offers the runtime namespaces (and
    optionally system and extra components)."""
    repo = root / "repo"
    components: dict = {}
    if with_system:
        sys_pack = repo / "packs" / "y5n-packs-system"
        source_pack(sys_pack, "y5n-packs-system", "/usr/bin")
        (sys_pack / "structure" / "bin").mkdir(parents=True)
        (sys_pack / "structure" / "bin" / "ls").write_text("echo hi\n")
        components["y5n-packs-system"] = {"location": "packs/y5n-packs-system"}
    root_pack = repo / "packs" / "y5n-packs-root"
    source_pack(root_pack, "y5n-packs-root", "/")
    (root_pack / "structure" / ".yak").mkdir(parents=True)
    (root_pack / "structure" / "usr").mkdir(parents=True)
    boot_pack = repo / "runtime" / "y5n-runtime-boot"
    source_pack(boot_pack, "y5n-runtime-boot", "/boot")
    components["y5n-packs-root"] = {"location": "packs/y5n-packs-root"}
    components["y5n-runtime-boot"] = {"location": "runtime/y5n-runtime-boot"}
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


def test_install_stages_platform_components(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)

        for name in ("y5n-packs-root", "y5n-runtime-boot"):
            staged = inst / ".yak" / "components" / name / "structure"
            assert staged.is_symlink()

        env = load_env(inst)
        assert env is not None
        assert env.components == [
            PackName("y5n-packs-root"),
            PackName("y5n-runtime-boot"),
        ]
        assert all(
            m.source.startswith(str(inst / ".yak" / "components")) for m in env.mounts
        )

        state = mgr.load(inst)
        assert state is not None
        assert [c.name for c in state.components] == [
            "y5n-packs-root",
            "y5n-runtime-boot",
        ]


def test_add_source_pack_is_source_linked(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("y5n-packs-system", inst)

        staged = inst / ".yak" / "components" / "y5n-packs-system" / "structure"
        assert staged.is_symlink()
        assert (
            staged.resolve()
            == (root / "repo" / "packs" / "y5n-packs-system" / "structure").resolve()
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
        record = next(c for c in state.components if c.name == "y5n-packs-system")
        assert record.mode == "source"
        assert record.source == str(
            root / "repo" / "packs" / "y5n-packs-system" / "structure"
        )


def test_workspace_points_at_component_store_only(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("y5n-packs-system", inst)

        prefix = str(inst / ".yak" / "components")
        for entry in (inst / "structure").rglob("*"):
            if entry.is_symlink():
                assert str(entry.readlink()).startswith(prefix), entry


def test_artifact_component_survives_store_deletion(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        make_artifact(repo / "artifacts" / "erp-art", "erp", "/opt/erp", "content")
        make_source(
            repo,
            {"erp": {"location": "artifacts/erp-art"}},
            environments={"test": "environments/test.yml"},
        )
        make_environment(repo, "test", [])
        ctx = Context(path=root, sources=[str(repo)], environment="test")
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("erp", inst)

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        assert (staged / "payload.txt").read_text() == "content"

        # GOLD: removing the source resource must not break the component.
        shutil.rmtree(repo / "artifacts" / "erp-art")

        assert (staged / "payload.txt").read_text() == "content"
        ws = inst / "structure" / "opt" / "erp"
        assert ws.is_symlink()
        assert (ws / "payload.txt").read_text() == "content"

        issues = mgr.doctor(inst)
        assert any("erp" in i and "✓" in i for i in issues)


def test_doctor_detects_dangling_source_component(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("y5n-packs-system", inst)

        shutil.rmtree(root / "repo" / "packs" / "y5n-packs-system" / "structure")

        issues = mgr.doctor(inst)
        assert any("dangling" in i for i in issues)


def test_update_artifact_refreshes_component(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        make_artifact(repo / "artifacts" / "erp-art", "erp", "/opt/erp", "v1")
        make_source(
            repo,
            {"erp": {"location": "artifacts/erp-art"}},
            environments={"test": "environments/test.yml"},
        )
        make_environment(repo, "test", [])
        ctx = Context(path=root, sources=[str(repo)], environment="test")
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        inst = root / "inst"
        mgr.install(inst)
        mgr.add("erp", inst)

        staged = inst / ".yak" / "components" / "erp" / "structure"
        assert (staged / "payload.txt").read_text() == "v1"

        # The source now holds v2 (new content + fingerprint).
        make_artifact(
            repo / "artifacts" / "erp-art", "erp", "/opt/erp", "v2", fingerprint="new"
        )

        mgr.update(inst)

        # Same canonical path, refreshed content + identity.
        assert staged.exists()
        assert (staged / "payload.txt").read_text() == "v2"
        state = mgr.load(inst)
        assert state is not None
        record = next(c for c in state.components if c.name == "erp")
        assert record.fingerprint == "new"
        assert record.mount == "/opt/erp"


def test_install_and_bootstrap_share_installation_structure(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mgr = _platform_mgr(root, monkeypatch)
        installed = root / "installed"
        bootstrapped = root / "source-checkout"
        mgr.install(installed)
        mgr.install(bootstrapped, workspace_path="workspace/structure")

        # The same installation model: same .yak structure.
        for sub in ("state.toml", "environment.yml", "deployment.yml"):
            assert (installed / ".yak" / sub).exists()
            assert (bootstrapped / ".yak" / sub).exists()
        assert sorted(
            p.name for p in (installed / ".yak" / "components").iterdir()
        ) == [
            "y5n-packs-root",
            "y5n-runtime-boot",
        ]
        assert sorted(
            p.name for p in (bootstrapped / ".yak" / "components").iterdir()
        ) == ["y5n-packs-root", "y5n-runtime-boot"]

        # Same SOLL/IST; only the workspace layout differs.
        env_inst = load_env(installed)
        env_boot = load_env(bootstrapped)
        assert env_inst is not None and env_boot is not None
        assert (
            env_inst.components
            == env_boot.components
            == [
                PackName("y5n-packs-root"),
                PackName("y5n-runtime-boot"),
            ]
        )
        assert env_inst.workspace_path == "structure"
        assert env_boot.workspace_path == "workspace/structure"

        st_inst = mgr.load(installed)
        st_boot = mgr.load(bootstrapped)
        assert st_inst is not None and st_boot is not None
        assert [c.name for c in st_inst.components] == [
            "y5n-packs-root",
            "y5n-runtime-boot",
        ]
        assert [c.name for c in st_boot.components] == [
            "y5n-packs-root",
            "y5n-runtime-boot",
        ]
        assert all(c.mode == "source" for c in st_boot.components)


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
