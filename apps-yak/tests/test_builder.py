"""Tests for builder module — project discovery via pyproject.toml."""

from __future__ import annotations

import tempfile
from pathlib import Path

from y5n.apps.yak.builder.workflow import _find_buildable_projects


def _make_pack(root: Path, name: str) -> Path:
    """Create a minimal Python component with pyproject.toml."""
    p = root / name
    p.mkdir()
    (p / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n[project]\nname = "'
        + name
        + '"\nversion = "0.1"\n'
    )
    return p


def _make_app(root: Path, name: str, buildable: bool = True) -> Path:
    """Create a Python project with or without build-system."""
    p = root / name
    p.mkdir()
    if buildable:
        (p / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n'
        )
    else:
        (p / "pyproject.toml").write_text('[project]\nname = "unbuildable"\n')
    return p


class TestFindBuildableProjects:
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _find_buildable_projects(Path(tmp))
            assert result == []

    def test_single_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pack(Path(tmp), "hello")
            result = _find_buildable_projects(Path(tmp))
            assert len(result) == 1
            assert result[0].name == "hello"

    def test_multiple_packs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pack(Path(tmp), "alpha")
            _make_pack(Path(tmp), "beta")
            result = _find_buildable_projects(Path(tmp))
            assert len(result) == 2
            names = {p.name for p in result}
            assert names == {"alpha", "beta"}

    def test_nested_packs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pack(Path(tmp), "root")
            sub = Path(tmp) / "subdir"
            sub.mkdir()
            _make_pack(sub, "nested")
            result = _find_buildable_projects(Path(tmp))
            assert len(result) == 2

    def test_pack_detected_via_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pack(Path(tmp), "demo")
            result = _find_buildable_projects(Path(tmp))
            assert len(result) == 1
            assert result[0].name == "demo"

    def test_mount_without_pyproject_not_buildable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "structure-only"
            p.mkdir()
            (p / ".yak").mkdir()
            (p / ".yak" / "mount.yml").write_text("path: /opt/x\n")
            result = _find_buildable_projects(Path(tmp))
            assert result == []

    def test_app_detected_via_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_app(Path(tmp), "myapp", buildable=True)
            result = _find_buildable_projects(Path(tmp))
            assert len(result) == 1
            assert result[0].name == "myapp"

    def test_unbuildable_pyproject_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_app(Path(tmp), "lib", buildable=False)
            result = _find_buildable_projects(Path(tmp))
            assert result == []

    def test_mixed_packs_and_apps(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pack(Path(tmp), "mypack")
            _make_app(Path(tmp), "myapp", buildable=True)
            _make_app(Path(tmp), "lib", buildable=False)
            result = _find_buildable_projects(Path(tmp))
            assert len(result) == 2
            names = {p.name for p in result}
            assert names == {"mypack", "myapp"}

    def test_dot_directories_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            hidden = Path(tmp) / ".hidden"
            hidden.mkdir()
            (hidden / "pyproject.toml").write_text(
                '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n'
            )
            _make_pack(Path(tmp), "visible")
            result = _find_buildable_projects(Path(tmp))
            assert len(result) == 1
            assert result[0].name == "visible"

    def test_nonexistent_root(self):
        result = _find_buildable_projects(Path("/nonexistent/path"))
        assert result == []
