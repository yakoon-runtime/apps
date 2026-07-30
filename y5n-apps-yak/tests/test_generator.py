"""Tests for generator module — create_pack, create_command."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.generator.command import _find_pack_root, create_command
from y5n.apps.yak.generator.pack import create_pack


@pytest.fixture(autouse=True)
def _preserve_cwd():
    original = Path.cwd()
    yield
    os.chdir(original)


class TestCreatePack:
    def test_create_pack_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_pack("hello", target=Path(tmp))
            assert (root / "pack.toml").exists()
            assert (root / "pyproject.toml").exists()
            assert (root / "README.md").exists()
            assert (root / "src" / "y5n" / "packs" / "hello" / "__init__.py").exists()
            assert (root / "structure" / ".yak" / "yak.yml").exists()

            yml = (root / "structure" / ".yak" / "yak.yml").read_text()
            assert "resolvable: false" in yml
            assert "navigable: true" in yml

            toml = (root / "pack.toml").read_text()
            assert 'name = "hello"' in toml

    def test_create_pack_respects_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "subdir"
            root = create_pack("demo", target=target)
            assert root.parent == target
            assert root.name == "demo"

    def test_create_pack_raises_if_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_pack("existing", target=Path(tmp))
            with pytest.raises(FileExistsError, match="already exists"):
                create_pack("existing", target=Path(tmp))

    def test_create_pack_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_pack("demo", target=Path(tmp))
            (root / "extra.txt").write_text("user file")
            root2 = create_pack("demo", target=Path(tmp), force=True)
            assert root2 == root
            assert (root / "pack.toml").exists()
            assert (root / "extra.txt").exists()


class TestFindPackRoot:
    def test_find_pack_root_from_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_pack("mypack", target=root)
            pack_dir = root / "mypack"
            subdir = pack_dir / "some" / "nested" / "path"
            subdir.mkdir(parents=True)

            found = _find_pack_root(subdir)
            assert found is not None
            assert found[0] == pack_dir
            assert found[1] == "mypack"

    def test_find_pack_root_from_pack_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_pack("mypack", target=root)
            pack_dir = root / "mypack"
            found = _find_pack_root(pack_dir)
            assert found is not None
            assert found[0] == pack_dir

    def test_find_pack_root_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = _find_pack_root(Path(tmp))
            assert found is None


class TestCreateCommand:
    def test_create_command_adds_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_root = create_pack("demo", target=Path(tmp))
            os.chdir(pack_root)
            structure_dir = create_command("greet", pack_name="demo", force=False)
            assert structure_dir.parent.name == "structure"
            assert structure_dir.name == "greet"

            assert (structure_dir / ".yak" / "yak.yml").exists()
            assert (structure_dir / "resources" / "default.ydf").exists()
            assert (structure_dir / "resources" / "man.ydf").exists()

            entry = pack_root / "src" / "y5n" / "packs" / "demo" / "greet.py"
            assert entry.exists()
            assert "async def main():" in entry.read_text()

            yml = (structure_dir / ".yak" / "yak.yml").read_text()
            assert "pack:y5n.packs.demo.greet:main" in yml

    def test_create_command_auto_detects_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_root = create_pack("auto", target=Path(tmp))
            os.chdir(pack_root)
            structure_dir = create_command("testcmd", force=False)
            assert structure_dir.name == "testcmd"

    def test_create_command_raises_if_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_root = create_pack("demo", target=Path(tmp))
            os.chdir(pack_root)
            create_command("existing", pack_name="demo", force=False)
            with pytest.raises(FileExistsError, match="already exists"):
                create_command("existing", pack_name="demo", force=False)

    def test_create_command_raises_if_no_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(Path(tmp))
            with pytest.raises(RuntimeError, match="no pack found"):
                create_command("orphan", pack_name=None)
