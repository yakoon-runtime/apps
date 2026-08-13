"""ADR-20 gold test: Yak materializes the environment the source index offers.

Yak knows no component names. A source catalog provides the artifacts of
an environment; ``install`` materializes them and a reconciled ``update``
converges to a changed desired state — with no installer change, because
the environment is fully declarative.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from conftest import artifact as make_artifact
from conftest import environment as make_environment
from conftest import make_source
from y5n.apps.yak.environment.io import load as load_env
from y5n.apps.yak.environment.io import touch
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _build_repo(root: Path, names: list[str], env_components: list[str]) -> Path:
    repo = root / "repo"
    components = {name: {"location": f"artifacts/{name}-art"} for name in names}
    for name in names:
        make_artifact(repo / "artifacts" / f"{name}-art", name, f"/opt/{name}")
    make_environment(repo, "fake", env_components)
    make_source(repo, components, environments={"fake": "environments/fake.yml"})
    return repo


def _mgr(root: Path, repo: Path) -> InstallationManager:
    ctx = Context(path=root, sources=[str(repo)], environment="fake")
    return InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=ctx,
    )


def test_install_materializes_arbitrary_environment():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _build_repo(root, ["foo", "bar", "baz"], ["foo", "bar", "baz"])
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst")

        state = mgr.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["bar", "baz", "foo"]
        assert all(c.mode == "artifact" for c in state.components)
        for name in ("foo", "bar", "baz"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir() and not staged.is_symlink()

        env = load_env(inst.root)
        assert env is not None
        assert sorted(str(c) for c in env.components) == ["bar", "baz", "foo"]


def test_update_converges_to_changed_environment():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _build_repo(root, ["foo", "bar", "baz"], ["foo", "bar", "baz"])
        mgr = _mgr(root, repo)
        inst = mgr.install(root / "inst")

        # The desired state changes to foo + quux: the source grows quux,
        # and the materialized SOLL is edited accordingly.
        make_artifact(repo / "artifacts" / "quux-art", "quux", "/opt/quux")
        make_source(
            repo,
            {
                "foo": {"location": "artifacts/foo-art"},
                "quux": {"location": "artifacts/quux-art"},
            },
            environments={"fake": "environments/fake.yml"},
        )
        make_environment(repo, "fake", ["foo", "quux"])
        touch(inst.root, name="fake", components=["foo", "quux"])

        mgr2 = _mgr(root, repo)
        mgr2.update(inst.root)

        state = mgr2.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["foo", "quux"]
        for name in ("foo", "quux"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir()
        for name in ("bar", "baz"):
            assert not (inst.root / ".yak" / "components" / name).exists()
