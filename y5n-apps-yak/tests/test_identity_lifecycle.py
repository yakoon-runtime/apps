"""Bundle-first lifecycle (ADR-21): build/publish/deploy expand identities.

The public lifecycle identity is a bundle: ``runtime`` expands to its
component names via the shared index, and each command then runs the
existing per-component mechanism. A bundle has no version, no artifact,
no state — it is resolved and disappears. ``build`` keeps a path escape
hatch; ``--to`` stays a single-component feature.
"""

from __future__ import annotations

import tempfile
import types
from pathlib import Path

import pytest
from conftest import make_source
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _repo(root: Path) -> Path:
    repo = root / "repo"
    for name in ("a", "b"):
        (repo / name).mkdir(parents=True)
    make_source(
        repo,
        {"a": {"location": "a"}, "b": {"location": "b"}},
        bundles={"runtime": ["a", "b"]},
    )
    return repo


def _mgr(root: Path, repo: Path) -> InstallationManager:
    ctx = Context(path=root, sources=[str(repo)])
    return InstallationManager(FileRepository(), DirectoryArtifactStore(), context=ctx)


def _args(**kw) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


def test_bundle_members_expand_only_bundles():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        repo = _repo(base)
        mgr = _mgr(base, repo)
        assert mgr._bundle_members("runtime") == ["a", "b"]
        assert mgr._bundle_members("a") == ["a"]  # a component passes through
        assert mgr._bundle_members("unknown") == ["unknown"]  # never raises


def test_build_expands_bundle_to_member_sources(monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import build as build_cmd

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        repo = _repo(base)
        mgr = _mgr(base, repo)

        calls: list[Path] = []
        monkeypatch.setattr(
            build_cmd,
            "build_workflow",
            lambda *, project_dir: calls.append(project_dir) or True,
        )
        build_cmd.run(_args(source="runtime"), mgr)

        assert sorted(str(p.resolve()) for p in calls) == sorted(
            [
                str((base / "repo" / "a").resolve()),
                str((base / "repo" / "b").resolve()),
            ]
        )


def test_build_path_is_escape_hatch(monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import build as build_cmd

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        repo = _repo(base)
        mgr = _mgr(base, repo)

        calls: list[Path] = []
        monkeypatch.setattr(
            build_cmd,
            "build_workflow",
            lambda *, project_dir: calls.append(project_dir) or True,
        )
        build_cmd.run(_args(source=str(base / "repo" / "a")), mgr)

        assert [str(p.resolve()) for p in calls] == [
            str((base / "repo" / "a").resolve())
        ]


def test_publish_expands_bundle(monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import publish as publish_cmd

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        repo = _repo(base)
        mgr = _mgr(base, repo)

        calls: list[str] = []
        monkeypatch.setattr(
            publish_cmd, "publish_local", lambda name: calls.append(name) or "/store"
        )
        publish_cmd.run(_args(name="runtime"), mgr)

        assert calls == ["a", "b"]


def test_deploy_expands_bundle_to_member_homes(monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import deploy as deploy_cmd

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        repo = _repo(base)
        mgr = _mgr(base, repo)

        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(
            deploy_cmd,
            "deploy_artifact",
            lambda name, target: calls.append((name, target)) or True,
        )
        deploy_cmd.run(_args(name="runtime", to=None), mgr)

        # Both members deploy to their shared home catalog.
        assert calls == [("a", str(base / "repo")), ("b", str(base / "repo"))]


def test_deploy_rejects_to_for_a_bundle(monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import deploy as deploy_cmd

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        repo = _repo(base)
        mgr = _mgr(base, repo)

        calls: list = []
        monkeypatch.setattr(
            deploy_cmd,
            "deploy_artifact",
            lambda name, target: calls.append((name, target)) or True,
        )
        deploy_cmd.run(_args(name="runtime", to="github:acme/packs"), mgr)

        assert calls == []
