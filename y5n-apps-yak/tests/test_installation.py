import tempfile
from pathlib import Path

import pytest
from conftest import make_source, source_pack
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _make_env(root):
    repo = root / "repo"
    source_pack(repo / "acme-root", "acme-root", "/")
    source_pack(repo / "test-pack", "test-pack", "/test-pack")
    make_source(
        repo,
        {
            "acme-root": {"location": "acme-root"},
            "test-pack": {"location": "test-pack"},
        },
        bundles={"platform": ["acme-root"]},
    )
    return repo


def _mgr(root, repo):
    ctx = Context(path=root, sources=[str(repo)])
    return InstallationManager(FileRepository(), DirectoryArtifactStore(), context=ctx)


@pytest.mark.slow
def test_install_creates_platform_installation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        inst = mgr.install(inst_path, identity="platform", paths=[str(repos)])

        assert inst is not None
        assert inst.name == "inst"
        assert "acme-root" in inst.packs
        assert inst.root == inst_path
        assert (inst.root / "workspace.toml").exists()
        assert (inst.root / ".yak" / "state.toml").exists()
        assert (inst.root / ".yak" / "deployment.yml").exists()
        # The platform binds the runtime's own store, no packs.
        from y5n.runtime.engine.installation import load_installation

        deployment = load_installation(inst.root / ".yak" / "deployment.yml")
        assert deployment is not None
        assert set(deployment.stores) == {"runtime"}


@pytest.mark.slow
def test_install_extends_the_platform():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path, identity="platform", paths=[str(repos)])
        added = mgr.install(inst_path, identity="test-pack", paths=[str(repos)])

        assert added is not None
        assert "test-pack" in added.packs
        # Idempotent: installing again reports nothing new.
        assert (
            mgr.install(inst_path, identity="test-pack", paths=[str(repos)]) is None
        )


@pytest.mark.slow
def test_install_unknown_identity_raises():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path, identity="platform", paths=[str(repos)])

        with pytest.raises(ValueError, match="Unknown identity"):
            mgr.install(inst_path, identity="nonexistent")


@pytest.mark.slow
def test_load_from_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path, identity="platform", paths=[str(repos)])

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


@pytest.mark.slow
def test_update_reconciles():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path, identity="platform", paths=[str(repos)])
        mgr.install(inst_path, identity="test-pack", paths=[str(repos)])
        mgr.update(inst_path)

        loaded = mgr.load(inst_path)
        assert loaded is not None
        assert loaded.status.value == "created"
        assert "test-pack" in loaded.packs


@pytest.mark.slow
def test_doctor_reports_missing_pack():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(root, repos)

        inst_path = root / "inst"
        mgr.install(inst_path, identity="platform", paths=[str(repos)])
        mgr.install(inst_path, identity="test-pack", paths=[str(repos)])

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
