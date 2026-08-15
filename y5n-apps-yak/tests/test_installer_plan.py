"""The installer plan: one pip transaction for a resolved component set.

Source and artifact are different origins of the same component; pip
receives both forms (wheel / editable) in ONE call and resolves the whole
graph at once. Reference cases: all artifact, all source, mixed,
extend, switch (exactly one active distribution), and hard failure —
a broken pip run must never report a successful state.
"""

from __future__ import annotations

import json
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
            "lib-a": {"location": "artifacts/lib-a", "release": "artifacts/lib-a"},
            "lib-b": {"location": "artifacts/lib-b", "release": "artifacts/lib-b"},
            "app": {"location": "artifacts/app", "release": "artifacts/app"},
        },
        bundles={"platform": ["app", "lib-a", "lib-b"]},
    )

    local = root / "local"
    source_proj(local / "projects" / "app", "app", "0.1.0", deps=("lib-a",))
    make_source(local, {"app": {"location": "projects/app"}})
    return remote, local


def _all_source(root: Path) -> Path:
    local = root / "local-all"
    source_proj(local / "app", "app", "0.1.0", deps=("lib-a",))
    source_proj(local / "lib-a", "lib-a", "0.1.0")
    source_proj(local / "lib-b", "lib-b", "0.1.0")
    make_source(
        local,
        {
            "app": {"location": "app"},
            "lib-a": {"location": "lib-a"},
            "lib-b": {"location": "lib-b"},
        },
        bundles={"platform": ["app", "lib-a", "lib-b"]},
    )
    return local


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
    data = json.loads(_pip(inst, "list", "--format=json").stdout)
    return {d["name"] for d in data}


def _is_editable(inst: Path, name: str) -> bool:
    return "Editable project location:" in _pip(inst, "show", name).stdout


def _pip_check(inst: Path) -> str:
    return _pip(inst, "check").stdout.strip()


@pytest.mark.slow
def test_all_artifact_installs_wheels():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, _ = _world(root)
        mgr = _mgr(root, [remote])
        inst = mgr.install(root / "inst", identity="platform")

        assert inst is not None
        assert _dist_names(inst.root) >= {"app", "lib-a", "lib-b"}
        assert not _is_editable(inst.root, "app")
        assert _pip_check(inst.root) == "No broken requirements found."


@pytest.mark.slow
def test_all_source_installs_editable():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        local = _all_source(root)
        mgr = _mgr(root, [])
        inst = mgr.install(root / "inst", identity="platform", paths=[str(local)])

        assert inst is not None
        assert _dist_names(inst.root) >= {"app", "lib-a", "lib-b"}
        assert _is_editable(inst.root, "app")
        assert _is_editable(inst.root, "lib-a")
        assert _pip_check(inst.root) == "No broken requirements found."


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


@pytest.mark.slow
def test_extend_source_over_release():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, local = _world(root)
        mgr = _mgr(root, [remote])
        inst = mgr.install(root / "inst", identity="platform")
        assert inst is not None
        assert not _is_editable(inst.root, "app")

        # Now develop app from a local checkout.
        mgr.install(inst.root, identity="app", paths=[str(local)])
        assert _is_editable(inst.root, "app")
        assert not _is_editable(inst.root, "lib-a")
        assert _pip_check(inst.root) == "No broken requirements found."


@pytest.mark.slow
def test_switch_back_to_artifact_keeps_one_distribution():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, local = _world(root)
        mgr = _mgr(root, [remote])
        inst = mgr.install(root / "inst", identity="platform")
        assert inst is not None

        mgr.install(inst.root, identity="app", paths=[str(local)])
        assert _is_editable(inst.root, "app")

        # Back to the release: the editable install is replaced.
        mgr.install(inst.root, identity="app")
        assert not _is_editable(inst.root, "app")
        assert _pip(inst.root, "show", "app").stdout.count("Name: app") == 1
        assert _pip_check(inst.root) == "No broken requirements found."


@pytest.mark.slow
def test_pip_failure_never_reports_success():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad = root / "bad"
        wheel_artifact(
            bad / "artifacts" / "broken", "broken", "0.1.0", deps=("no-such-pkg-xyz",)
        )
        make_source(
            bad,
            {"broken": {"location": "artifacts/broken", "release": "artifacts/broken"}},
            bundles={"bad": ["broken"]},
        )
        mgr = _mgr(root, [bad])

        with pytest.raises(RuntimeError, match="pip install failed"):
            mgr.install(root / "inst", identity="bad")

        # A failed pip run must leave no state: state.toml is the truth
        # about an established environment and is only written after a
        # successful install.
        assert mgr.load(root / "inst") is None
