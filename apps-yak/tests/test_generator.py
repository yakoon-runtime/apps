"""Tests for generator module — create_cap, create_command."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.generator.command import _find_cap_root, create_command
from y5n.apps.yak.generator.pack import create_cap


@pytest.fixture(autouse=True)
def _preserve_cwd():
    original = Path.cwd()
    yield
    os.chdir(original)


class TestCreateCap:
    def test_create_cap_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_cap("hello", target=Path(tmp))
            assert (root / "pyproject.toml").exists()
            assert not (root / "pack.toml").exists()
            assert (root / "README.md").exists()
            assert (root / "src" / "y5n" / "caps" / "hello" / "__init__.py").exists()
            assert (root / "structure" / ".yak" / "yak.yml").exists()

            yml = (root / "structure" / ".yak" / "yak.yml").read_text()
            assert "resolvable: false" in yml
            assert "navigable: true" in yml

            toml = (root / "pyproject.toml").read_text()
            assert 'name = "hello"' in toml

    def test_create_cap_respects_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "subdir"
            root = create_cap("demo", target=target)
            assert root.parent == target
            assert root.name == "demo"

    def test_create_cap_raises_if_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_cap("existing", target=Path(tmp))
            with pytest.raises(FileExistsError, match="already exists"):
                create_cap("existing", target=Path(tmp))

    def test_create_cap_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_cap("demo", target=Path(tmp))
            (root / "extra.txt").write_text("user file")
            root2 = create_cap("demo", target=Path(tmp), force=True)
            assert root2 == root
            assert (root / "pyproject.toml").exists()
            assert (root / "extra.txt").exists()


class TestFindCapRoot:
    def test_find_cap_root_from_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_cap("mypack", target=root)
            cap_dir = root / "mypack"
            subdir = cap_dir / "some" / "nested" / "path"
            subdir.mkdir(parents=True)

            found = _find_cap_root(subdir)
            assert found is not None
            assert found[0] == cap_dir
            assert found[1] == "mypack"

    def test_find_cap_root_from_cap_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_cap("mypack", target=root)
            cap_dir = root / "mypack"
            found = _find_cap_root(cap_dir)
            assert found is not None
            assert found[0] == cap_dir

    def test_find_cap_root_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = _find_cap_root(Path(tmp))
            assert found is None


class TestCreateCommand:
    def test_create_command_adds_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap_root = create_cap("demo", target=Path(tmp))
            os.chdir(cap_root)
            structure_dir = create_command("greet", cap_name="demo", force=False)
            assert structure_dir.parent.name == "structure"
            assert structure_dir.name == "greet"

            assert (structure_dir / ".yak" / "yak.yml").exists()
            assert (structure_dir / "resources" / "default.ydf").exists()
            assert (structure_dir / "resources" / "man.ydf").exists()

            entry = cap_root / "src" / "y5n" / "caps" / "demo" / "greet.py"
            assert entry.exists()
            assert "async def main():" in entry.read_text()

            yml = (structure_dir / ".yak" / "yak.yml").read_text()
            assert "cap:y5n.caps.demo.greet:main" in yml

    def test_create_command_auto_detects_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap_root = create_cap("auto", target=Path(tmp))
            os.chdir(cap_root)
            structure_dir = create_command("testcmd", force=False)
            assert structure_dir.name == "testcmd"

    def test_create_command_raises_if_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap_root = create_cap("demo", target=Path(tmp))
            os.chdir(cap_root)
            create_command("existing", cap_name="demo", force=False)
            with pytest.raises(FileExistsError, match="already exists"):
                create_command("existing", cap_name="demo", force=False)

    def test_create_command_raises_if_no_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(Path(tmp))
            with pytest.raises(RuntimeError, match="no cap found"):
                create_command("orphan", cap_name=None)
