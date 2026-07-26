"""Tests for context detection — find_context_root, find_installation_path."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.hosts.cli.cwd import find_context_root, find_installation_path


def _init(root: Path) -> None:
    (root / ".yak").mkdir(parents=True, exist_ok=True)
    (root / ".yak" / "context.toml").write_text('[context]\nname = "test"\n')


def _install(root: Path) -> None:
    (root / ".yak").mkdir(parents=True, exist_ok=True)
    (root / ".yak" / "state.toml").write_text('[installation]\nname = "test"\n')


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

    def test_context_toml_outside_state_toml(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            install_dir = root / "installed"
            install_dir.mkdir()
            _install(install_dir)
            monkeypatch.setattr(Path, "cwd", lambda: install_dir)
            assert find_context_root() == root  # outermost context.toml

    def test_state_toml_without_context(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install(root)
            monkeypatch.setattr(Path, "cwd", lambda: root)
            assert find_context_root() is None  # no context.toml


class TestFindInstallationPath:
    def test_from_installation_dir(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install(root)
            monkeypatch.setattr(Path, "cwd", lambda: root)
            assert find_installation_path() == root

    def test_prefers_nearest_state_toml(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            install_dir = root / "app"
            install_dir.mkdir()
            _install(install_dir)
            monkeypatch.setattr(Path, "cwd", lambda: install_dir)
            assert find_installation_path() == install_dir  # nearest state.toml

    def test_falls_back_to_context(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            monkeypatch.setattr(Path, "cwd", lambda: root)
            assert find_installation_path() == root

    def test_no_installation(self, fixed_cwd):
        assert find_installation_path() is None
