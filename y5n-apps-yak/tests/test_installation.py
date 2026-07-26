import tempfile
from pathlib import Path

from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _make_env(root, pack_name="test-pack"):
    repos = root / "repos"
    artifacts = root / "artifacts"
    (repos / pack_name / "structure").mkdir(parents=True)
    (repos / pack_name / "pack.toml").write_text(
        f'name = "{pack_name}"\nversion = "0.1"\n'
    )
    artifacts.mkdir()
    (artifacts / "myapp.yml").write_text(
        f'name: myapp\nversion: "0.1"\nkind: meta\nworkspace:\n  mounts:\n    - pack: {pack_name}\n      target: /\n'
    )
    return repos, artifacts


def _mgr(repos, artifacts):
    repo = FileRepository(repos, builtin_artifacts=artifacts)
    artifacts = DirectoryArtifactStore(repos)
    return InstallationManager(repo, artifacts)


def test_install_creates_installation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos, artifacts = _make_env(root)
        mgr = _mgr(repos, artifacts)

        inst_path = root / "inst" / "myapp"
        inst = mgr.install("myapp", inst_path)

        assert inst.name == "myapp"
        assert inst.distribution == "myapp"
        assert inst.packs == ["test-pack"]
        assert inst.root == inst_path
        assert (inst.root / "workspace.toml").exists()
        assert (inst.root / ".yak" / "state.toml").exists()


def test_install_unknown_target_raises():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = FileRepository(root / "repos", builtin_artifacts=root / "artifacts")
        artifacts = DirectoryArtifactStore(root / "repos")
        mgr = InstallationManager(repo, artifacts)

        import pytest

        with pytest.raises(ValueError, match="Unknown target"):
            mgr.install("nonexistent", root / "inst" / "nope")


def test_load_from_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos, artifacts = _make_env(root)
        mgr = _mgr(repos, artifacts)

        inst_path = root / "inst" / "myapp"
        mgr.install("myapp", inst_path)

        loaded = mgr.load(inst_path)
        assert loaded is not None
        assert loaded.name == "myapp"
        assert loaded.root == inst_path


def test_load_returns_none_for_invalid_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = FileRepository(root / "repos", builtin_artifacts=root / "artifacts")
        artifacts = DirectoryArtifactStore(root / "repos")
        mgr = InstallationManager(repo, artifacts)

        assert mgr.load(root / "nonexistent") is None


def test_update_rematerializes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos, artifacts = _make_env(root)
        mgr = _mgr(repos, artifacts)

        inst_path = root / "inst" / "myapp"
        mgr.install("myapp", inst_path)
        mgr.update(inst_path)
        loaded = mgr.load(inst_path)
        assert loaded is not None
        assert loaded.status.value == "created"


def test_doctor_reports_missing_pack():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos, artifacts = _make_env(root)
        mgr = _mgr(repos, artifacts)

        inst_path = root / "inst" / "myapp"
        mgr.install("myapp", inst_path)

        import shutil

        shutil.rmtree(repos / "test-pack")

        issues = mgr.doctor(inst_path)
        assert any("test-pack" in i for i in issues)


def test_doctor_reports_missing_installation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos, artifacts = _make_env(root)
        mgr = _mgr(repos, artifacts)
        issues = mgr.doctor(root / "nonexistent")
        assert "not found" in issues[0]


def test_update_unknown_raises():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repos, artifacts = _make_env(root)
        mgr = _mgr(repos, artifacts)
        import pytest

        with pytest.raises(ValueError, match="not found"):
            mgr.update(root / "nonexistent")
