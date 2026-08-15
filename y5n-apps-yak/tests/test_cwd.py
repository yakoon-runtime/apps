"""Tests for context detection — find_context_root."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.hosts.cli.cwd import find_context_root


def _init(root: Path) -> None:
    (root / ".yak").mkdir(parents=True, exist_ok=True)
    (root / ".yak" / "context.toml").write_text('[context]\nname = "test"\n')


@pytest.fixture
def fixed_cwd(monkeypatch):
    """Fixture that sets Path.cwd() to a temp dir without os.chdir."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(Path, "cwd", lambda: Path(tmp))
    yield Path(tmp)


class TestFindContextRoot:
    def test_from_context_dir(self, fixed_cwd):
        root = fixed_cwd
        _init(root)
        assert find_context_root() == root

    def test_from_subdirectory(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            sub = root / "a" / "b" / "c"
            sub.mkdir(parents=True)
            monkeypatch.setattr(Path, "cwd", lambda: sub)
            assert find_context_root() == root

    def test_no_context(self, fixed_cwd):
        assert find_context_root() is None

    def test_prefers_outermost_context(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            inner = root / "inner"
            inner.mkdir()
            _init(inner)
            sub = inner / "sub"
            sub.mkdir()
            monkeypatch.setattr(Path, "cwd", lambda: sub)
            assert find_context_root() == root  # outermost


def test_init_copies_packaged_default_context(monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import init_cmd

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        init_cmd._init(root)
        ctx = (root / ".yak" / "context.toml").read_text()
        assert "github:yakoon-runtime/pack-system" in ctx
        assert "github:yakoon-runtime/runtime" in ctx
        assert "github:yakoon-runtime/sdk" in ctx
        assert "github:yakoon-runtime/apps" in ctx
        assert "install" not in ctx
        assert "y5n-packs-root" not in ctx
        assert "yakoon:official" not in ctx
        assert 'name = "proj"' in ctx


def test_install_ensures_context_when_missing():
    from y5n.apps.yak.hosts.cli.commands.install import _ensure_context

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "demo"
        _ensure_context(root)
        ctx = root / ".yak" / "context.toml"
        assert ctx.exists()
        assert "github:yakoon-runtime/pack-system" in ctx.read_text()
        # A second call is a no-op.
        _ensure_context(root)
        assert ctx.exists()
