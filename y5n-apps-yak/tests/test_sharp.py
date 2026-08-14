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
    """Install the minimal platform, then add the crm pack."""
    root = Path(tempfile.mkdtemp(prefix="yak-sharp-"))
    try:
        repo_root = Path(__file__).resolve().parents[3]
        source = root / "repo"
        (source / "packs").mkdir(parents=True)
        (source / "packs" / "y5n-packs-crm").symlink_to(
            repo_root / "pack-crm", target_is_directory=True
        )
        from conftest import make_source

        make_source(source, {"y5n-packs-crm": {"location": "packs/y5n-packs-crm"}})
        ctx = Context(path=root, sources=[str(source)])
        mgr = InstallationManager(
            FileRepository(),
            DirectoryArtifactStore(),
            context=ctx,
        )

        inst = mgr.install(root / "installations" / "crm")
        assert inst.packs == []

        added = mgr.add("y5n-packs-crm", inst.root)
        assert added is not None
        assert "y5n-packs-crm" in added.packs

        print(f"Name:         {inst.name}")
        print(f"Status:       {inst.status.value}")
        print(f"Packs:        {', '.join(added.packs)}")
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
