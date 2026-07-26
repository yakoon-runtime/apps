"""Tests for context detection — find_context_root, find_installation_path."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from y5n.apps.yak.hosts.cli.cwd import find_context_root, find_installation_path


@pytest.fixture(autouse=True)
def _preserve_cwd():
    original = Path.cwd()
    yield
    os.chdir(original)


def _init(root: Path) -> None:
    (root / ".yak").mkdir(parents=True, exist_ok=True)
    (root / ".yak" / "context.toml").write_text("[context]\nname = \"test\"\n")


def _install(root: Path) -> None:
    (root / ".yak").mkdir(parents=True, exist_ok=True)
    (root / ".yak" / "state.toml").write_text("[installation]\nname = \"test\"\n")


class TestFindContextRoot:
    def test_from_context_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            os.chdir(root)
            assert find_context_root() == root

    def test_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            sub = root / "a" / "b" / "c"
            sub.mkdir(parents=True)
            os.chdir(sub)
            assert find_context_root() == root

    def test_no_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(Path(tmp))
            assert find_context_root() is None

    def test_prefers_outermost_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            inner = root / "inner"
            inner.mkdir()
            _init(inner)
            sub = inner / "sub"
            sub.mkdir()
            os.chdir(sub)
            assert find_context_root() == root  # outermost

    def test_context_toml_outside_state_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            install_dir = root / "installed"
            install_dir.mkdir()
            _install(install_dir)
            os.chdir(install_dir)
            assert find_context_root() == root  # outermost context.toml

    def test_state_toml_without_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install(root)
            os.chdir(root)
            assert find_context_root() is None  # no context.toml


class TestFindInstallationPath:
    def test_from_installation_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install(root)
            os.chdir(root)
            assert find_installation_path() == root

    def test_prefers_nearest_state_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            install_dir = root / "app"
            install_dir.mkdir()
            _install(install_dir)
            os.chdir(install_dir)
            assert find_installation_path() == install_dir  # nearest state.toml

    def test_falls_back_to_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init(root)
            os.chdir(root)
            assert find_installation_path() == root

    def test_no_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(Path(tmp))
            assert find_installation_path() is None
