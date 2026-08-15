"""Sharp test: minimal platform install + add crm outside the repo."""

import shutil
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


@pytest.mark.slow
def test_sharp_install():
    """Install a component from a local source catalog."""
    root = Path(tempfile.mkdtemp(prefix="yak-sharp-"))
    try:
        from conftest import make_source, source_pack

        source = root / "repo"
        source_pack(source / "cool-shell", "cool-shell", "/opt/cool")
        make_source(source, {"cool-shell": {"location": "cool-shell"}})
        ctx = Context(path=root, sources=[str(source)])
        mgr = InstallationManager(
            FileRepository(),
            DirectoryArtifactStore(),
            context=ctx,
        )

        inst = mgr.install(
            root / "installations" / "cool",
            identity="cool-shell",
            paths=[str(source)],
        )
        assert inst is not None
        assert "cool-shell" in inst.packs

        print(f"Name:         {inst.name}")
        print(f"Status:       {inst.status.value}")
        print(f"Packs:        {', '.join(inst.packs)}")
        print(f"Root:         {inst.root}")
        print()

        for child in sorted(inst.root.iterdir()):
            suffix = "/" if child.is_dir() else ""
            print(f"  {child.name}{suffix}")

        workspace = inst.root / "workspace.toml"
        assert workspace.exists()

        state = inst.root / ".yak" / "state.toml"
        assert state.exists()

        print()
        print("Sharp test passed.")
        print()
        print(f"Installation is at: {inst.root}")
        print("It will be deleted when this test finishes.")

    finally:
        shutil.rmtree(root)
