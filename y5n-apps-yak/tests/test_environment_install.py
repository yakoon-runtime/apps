"""ADR-8 gold test: Yak materializes the environment it was given.

Yak knows no component names. A fake repository provides the artifacts of
a fake environment; ``install`` materializes them and a reconciled
``update`` converges to a changed manifest — with no installer change,
because the environment is fully declarative.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _artifact(home: Path, name: str, mount: str = "/opt/x") -> None:
    store = home / ".yak" / "artifacts" / f"{name}-1.0.0.python.artifact"
    (store / "structure").mkdir(parents=True)
    (store / "structure" / "payload.txt").write_text(name)
    (store / "artifact.yml").write_text(
        "name: " + name + "\n"
        "version: 1.0.0\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        "mount: " + mount + "\n"
        "fingerprint: sha256:" + name + "\n"
    )


def _write_environment(home: Path, name: str, components: list[str]) -> None:
    env_dir = home / ".yak" / "artifacts" / "environments"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / f"{name}.yml").write_text(
        "name: "
        + name
        + "\nversion: 1.0.0\ncomponents:\n"
        + "".join(f"  - {c}\n" for c in components)
    )


def _mgr(home: Path) -> InstallationManager:
    ctx = Context(path=home, environment="fake")
    return InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=ctx,
    )


def test_install_materializes_arbitrary_environment(monkeypatch):
    monkeypatch.setattr(
        "y5n.apps.yak.resolver.install.install_artifact", lambda *a, **k: True
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        for name in ("foo", "bar", "baz"):
            _artifact(home, name, mount=f"/opt/{name}")
        _write_environment(home, "fake", ["foo", "bar", "baz"])

        mgr = _mgr(home)
        inst = mgr.install(root / "inst")

        # Yak materializes exactly what the manifest declares — no
        # platform knowledge, no hidden component list.
        state = mgr.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["bar", "baz", "foo"]
        assert all(c.mode == "artifact" for c in state.components)
        for name in ("foo", "bar", "baz"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir() and not staged.is_symlink()

        # The local environment is the materialized SOLL.
        from y5n.apps.yak.environment.io import load as load_env

        env = load_env(inst.root)
        assert env is not None
        assert sorted(str(c) for c in env.components) == ["bar", "baz", "foo"]


def test_update_converges_to_changed_environment(monkeypatch):
    monkeypatch.setattr(
        "y5n.apps.yak.resolver.install.install_artifact", lambda *a, **k: True
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        for name in ("foo", "bar", "baz"):
            _artifact(home, name, mount=f"/opt/{name}")
        _write_environment(home, "fake", ["foo", "bar", "baz"])

        mgr = _mgr(home)
        inst = mgr.install(root / "inst")

        # The desired state changes: foo + quux instead of foo/bar/baz.
        _artifact(home, "quux", mount="/opt/quux")
        _write_environment(home, "fake", ["foo", "quux"])
        from y5n.apps.yak.environment.io import load as load_env
        from y5n.apps.yak.environment.io import touch

        env = load_env(inst.root)
        assert env is not None
        touch(inst.root, name=env.name, components=["foo", "quux"])

        mgr.update(inst.root)

        state = mgr.load(inst.root)
        assert state is not None
        assert sorted(c.name for c in state.components) == ["foo", "quux"]
        for name in ("foo", "quux"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir()
        for name in ("bar", "baz"):
            assert not (inst.root / ".yak" / "components" / name).exists()
