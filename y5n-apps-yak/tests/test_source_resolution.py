"""ADR-8 gold tests: Environment (WHAT) + Context (WHERE) → State (IST).

Four scenarios prove the source-resolution contract:

- A — Released: no mapping, the Environment pin resolves as an artifact.
- B — Development override: a ``[sources]`` mapping makes the component a
  source; the executed payload is the checkout.
- C — Return: removing the mapping and ``yak update`` restores the artifact.
- D — Platform is ordinary: root/boot resolve as plain artifacts with no
  monorepo paths and no platform special-casing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _empty_mgr() -> InstallationManager:
    """A manager with no sources, no repositories, no platform roots."""
    return InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
    )


def _write_artifact(
    home: Path,
    name: str,
    version: str,
    fingerprint: str,
    content: str,
    mount: str = "/opt/x",
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
        "mount: " + mount + "\n"
        "fingerprint: " + fingerprint + "\n"
    )
    return store


def _source_pack(src: Path, name: str, version: str, mount: str) -> Path:
    pack = src / name
    (pack / "structure").mkdir(parents=True)
    (pack / "structure" / "payload.txt").write_text(f"{name}-source")
    (pack / "pack.toml").write_text(
        f'name = "{name}"\nversion = "{version}"\nmount = "{mount}"\n'
    )
    return pack


def test_a_released_resolves_artifact(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "crm", "0.8.0", "sha256:crm", "crm-artifact")

        mgr = _empty_mgr()
        inst = mgr.install(root / "inst")
        added = mgr.add("crm", inst.root)

        assert added is not None
        state = mgr.load(inst.root)
        assert state is not None
        records = [c for c in state.components if c.name == "crm"]
        assert len(records) == 1
        assert records[0].mode == "artifact"
        assert records[0].version == "0.8.0"
        staged = inst.root / ".yak" / "components" / "crm" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        assert (staged / "payload.txt").read_text() == "crm-artifact"


def test_b_development_override_runs_the_checkout(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "crm", "0.8.0", "sha256:crm", "crm-artifact")
        src = root / "src"
        pack = _source_pack(src, "crm", "0.9.0", "/opt/crm")

        ctx = Context(
            path=root,
            component_sources={"crm": "src/crm"},
        )
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        inst = mgr.install(root / "inst")
        mgr.add("crm", inst.root)

        state = mgr.load(inst.root)
        assert state is not None
        record = next(c for c in state.components if c.name == "crm")
        # Source wins over the Environment/artifact — the next version runs.
        assert record.mode == "source"
        assert record.source == str(pack / "structure")
        staged = inst.root / ".yak" / "components" / "crm" / "structure"
        assert staged.is_symlink()
        assert staged.resolve() == (pack / "structure").resolve()
        # The executed payload is the checkout, not the artifact.
        assert (staged / "payload.txt").read_text() == "crm-source"


def test_c_removing_mapping_returns_to_released(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(home, "crm", "0.8.0", "sha256:crm", "crm-artifact")
        _source_pack(root / "src", "crm", "0.9.0", "/opt/crm")

        ctx_dev = Context(
            path=root,
            component_sources={"crm": "src/crm"},
        )
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx_dev
        )
        inst = mgr.install(root / "inst")
        mgr.add("crm", inst.root)

        staged = inst.root / ".yak" / "components" / "crm" / "structure"
        assert staged.is_symlink()

        # Remove the override: same installation, same Environment, a
        # Context without the mapping. `yak update` falls back to the pin.
        ctx_released = Context(path=root)
        mgr2 = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx_released
        )
        mgr2.update(inst.root)

        state = mgr2.load(inst.root)
        assert state is not None
        records = [c for c in state.components if c.name == "crm"]
        assert len(records) == 1  # exactly one record
        assert records[0].mode == "artifact"
        assert records[0].version == "0.8.0"
        assert staged.is_dir() and not staged.is_symlink()
        assert (staged / "payload.txt").read_text() == "crm-artifact"


def test_d_platform_is_ordinary(monkeypatch):
    """root and boot resolve as plain artifacts — no parents[8], no shim."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        _write_artifact(
            home, "y5n-packs-root", "0.1.0", "sha256:root", "root-content", mount="/"
        )
        _write_artifact(
            home,
            "y5n-runtime-boot",
            "0.1.0",
            "sha256:boot",
            "boot-content",
            mount="/boot",
        )
        env_dir = home / ".yak" / "artifacts" / "environments"
        env_dir.mkdir(parents=True, exist_ok=True)
        (env_dir / "test.yml").write_text(
            "name: test\ncomponents:\n  - y5n-packs-root\n  - y5n-runtime-boot\n"
        )
        ctx = Context(path=root, environment="test")
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        inst = mgr.install(root / "inst")

        assert [str(p) for p in inst.packs] == [
            "y5n-packs-root",
            "y5n-runtime-boot",
        ]
        state = mgr.load(inst.root)
        assert state is not None
        assert [c.name for c in state.components] == [
            "y5n-packs-root",
            "y5n-runtime-boot",
        ]
        assert all(c.mode == "artifact" for c in state.components)
        for name in ("y5n-packs-root", "y5n-runtime-boot"):
            staged = inst.root / ".yak" / "components" / name / "structure"
            assert staged.is_dir() and not staged.is_symlink()
