"""The installer contract: one pip transaction for a mixed component set.

Exactly one integration test runs real pip against a created venv: a
mixed install (app editable + artifact wheels) resolves in one call,
lands both distributions and leaves ``pip check`` clean — the exact
failure we had with two-phase installs. The hard-failure contract (a
failed pip run must never report a state) is tested hermetically with a
mocked installer, without creating a venv.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
from conftest import make_source, source_proj, wheel_artifact
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _world(root: Path):
    """remote: app/lib-a/lib-b as wheels; local: app as a source project."""
    remote = root / "remote"
    wheel_artifact(remote / "artifacts" / "lib-a", "lib-a", "0.1.0")
    wheel_artifact(remote / "artifacts" / "lib-b", "lib-b", "0.1.0")
    wheel_artifact(remote / "artifacts" / "app", "app", "0.1.0", deps=("lib-a",))
    make_source(
        remote,
        {
            "lib-a": {"location": "artifacts/lib-a"},
            "lib-b": {"location": "artifacts/lib-b"},
            "app": {"location": "artifacts/app"},
        },
        bundles={"platform": ["app", "lib-a", "lib-b"]},
    )

    local = root / "local"
    source_proj(local / "projects" / "app", "app", "0.1.0", deps=("lib-a",))
    make_source(local, {"app": {"location": "projects/app"}})
    return remote, local


def _mgr(root: Path, sources) -> InstallationManager:
    ctx = Context(path=root, sources=[str(s) for s in sources])
    return InstallationManager(
        FileRepository(), DirectoryArtifactStore(), context=ctx
    )


def _pip(inst: Path, *args):
    return subprocess.run(
        [str(inst / ".venv" / "bin" / "python"), "-m", "pip", *args],
        capture_output=True,
        text=True,
    )


def _dist_names(inst: Path) -> set[str]:
    import json

    data = json.loads(_pip(inst, "list", "--format=json").stdout)
    return {d["name"] for d in data}


def _is_editable(inst: Path, name: str) -> bool:
    return "Editable project location:" in _pip(inst, "show", name).stdout


def _pip_check(inst: Path) -> str:
    return _pip(inst, "check").stdout.strip()


@pytest.mark.slow
def test_mixed_one_transaction():
    """app from source, lib-a/lib-b from releases — one pip call resolves all."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, local = _world(root)
        mgr = _mgr(root, [remote])
        inst = mgr.install(root / "inst", identity="platform", paths=[str(local)])

        assert inst is not None
        assert _dist_names(inst.root) >= {"app", "lib-a", "lib-b"}
        assert _is_editable(inst.root, "app")
        assert not _is_editable(inst.root, "lib-a")
        assert not _is_editable(inst.root, "lib-b")
        assert _pip_check(inst.root) == "No broken requirements found."


def test_pip_failure_leaves_no_state(monkeypatch):
    """A failed pip run must never report a state — tested with a mocked
    installer so no venv is created."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad = root / "bad"
        wheel_artifact(
            bad / "artifacts" / "broken", "broken", "0.1.0", deps=("no-such-pkg-xyz",)
        )
        make_source(
            bad,
            {"broken": {"location": "artifacts/broken"}},
            bundles={"bad": ["broken"]},
        )
        mgr = _mgr(root, [bad])

        def boom(self, path, candidates):
            raise RuntimeError("pip install failed")

        monkeypatch.setattr(type(mgr._installer), "install", boom)

        with pytest.raises(RuntimeError, match="pip install failed"):
            mgr.install(root / "inst", identity="bad")

        assert mgr.load(root / "inst") is None
        assert not (root / "inst" / ".yak" / "components" / "broken").exists()
