import tempfile
from pathlib import Path

from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _make_env(root, pack_name="test-pack"):
    repos = root / "repos"
    (repos / f"y5n-packs-{pack_name}" / "structure").mkdir(parents=True)
    (repos / f"y5n-packs-{pack_name}" / "pack.toml").write_text(
        f'name = "{pack_name}"\nversion = "0.1"\n'
    )
    return repos


def _mgr(repos):
    repo = FileRepository(repos)
    artifacts = DirectoryArtifactStore(repos)
    return InstallationManager(repo, artifacts)


def test_install_creates_platform_installation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(repos)

        inst_path = root / "inst"
        inst = mgr.install(inst_path)

        assert inst.name == "inst"
        assert inst.distribution == "yakoon"
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
        mgr = _mgr(repos)

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
        mgr = _mgr(repos)

        inst_path = root / "inst"
        mgr.install(inst_path)

        import pytest

        with pytest.raises(ValueError, match="Unknown component"):
            mgr.add("nonexistent", inst_path)


def test_add_rejects_development_templates():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        artifacts_dir = root / "artifacts"
        artifacts_dir.mkdir()
        (artifacts_dir / "dev.yml").write_text(
            "name: dev\nkind: development\ndependencies: []\nworkspace:\n  mounts: []\n"
        )
        repo = FileRepository(repos, builtin_artifacts=artifacts_dir)
        artifacts = DirectoryArtifactStore(repos)
        mgr = InstallationManager(repo, artifacts)

        inst_path = root / "inst"
        mgr.install(inst_path)

        import pytest

        with pytest.raises(ValueError, match="development environment"):
            mgr.add("dev", inst_path)


def test_load_from_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(repos)

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
        mgr = _mgr(repos)

        assert mgr.load(root / "nonexistent") is None


def test_update_reconciles():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(repos)

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
        mgr = _mgr(repos)

        inst_path = root / "inst"
        mgr.install(inst_path)
        mgr.add("test-pack", inst_path)

        import shutil

        shutil.rmtree(repos / "y5n-packs-test-pack")

        issues = mgr.doctor(inst_path)
        assert any("test-pack" in i for i in issues)


def test_doctor_reports_missing_installation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(repos)
        issues = mgr.doctor(root / "nonexistent")
        assert "not found" in issues[0]


def test_update_unknown_raises():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos = _make_env(root)
        mgr = _mgr(repos)
        import pytest

        with pytest.raises(ValueError, match="not found"):
            mgr.update(root / "nonexistent")
