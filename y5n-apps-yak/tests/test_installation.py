import tempfile
from pathlib import Path

from conftest import make_source, source_pack
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _make_env(root, pack_name="test-pack"):
    repo = root / "repo"
    source_pack(repo / pack_name, pack_name, f"/{pack_name}")
    make_source(repo, {pack_name: {"location": pack_name}})
    return repo


def _mgr(root, repo):
    ctx = Context(path=root, sources=[str(repo)])
    return InstallationManager(FileRepository(), DirectoryArtifactStore(), context=ctx)


def test_install_creates_platform_installation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        inst = mgr.install(inst_path)

        assert inst.name == "inst"
        assert inst.packs == []
        assert inst.root == inst_path
        assert (inst.root / "workspace.toml").exists()
        assert (inst.root / ".yak" / "state.toml").exists()
        assert (inst.root / ".yak" / "deployment.yml").exists()
        # The platform binds the runtime's own store, no packs.
        from y5n.runtime.engine.installation import load_installation

        deployment = load_installation(inst.root / ".yak" / "deployment.yml")
        assert deployment is not None
        assert set(deployment.stores) == {"runtime"}


def test_add_extends_the_platform():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path)
        added = mgr.add("test-pack", inst_path)

        assert added is not None
        assert "test-pack" in added.packs
        # Idempotent: adding again reports nothing new.
        assert mgr.add("test-pack", inst_path) is None


def test_add_unknown_component_raises():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path)

        import pytest

        with pytest.raises(ValueError, match="Unknown component"):
            mgr.add("nonexistent", inst_path)


def test_load_from_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path)

        loaded = mgr.load(inst_path)
        assert loaded is not None
        assert loaded.name == "inst"
        assert loaded.root == inst_path


def test_load_returns_none_for_invalid_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        assert mgr.load(root / "nonexistent") is None


def test_update_reconciles():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path)
        mgr.add("test-pack", inst_path)
        mgr.update(inst_path)

        loaded = mgr.load(inst_path)
        assert loaded is not None
        assert loaded.status.value == "created"
        assert "test-pack" in loaded.packs


def test_doctor_reports_missing_pack():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path)
        mgr.add("test-pack", inst_path)

        import shutil

        shutil.rmtree(repos / "test-pack")

        issues = mgr.doctor(inst_path)
        assert any("test-pack" in i for i in issues)


def test_doctor_reports_missing_installation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)
        issues = mgr.doctor(root / "nonexistent")
        assert "not found" in issues[0]


def test_update_unknown_raises():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)
        import pytest

        with pytest.raises(ValueError, match="not found"):
            mgr.update(root / "nonexistent")
