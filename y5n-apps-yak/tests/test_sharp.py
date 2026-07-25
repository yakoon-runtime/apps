"""Sharp test: yak install crm into an independent directory outside the repo."""

import shutil
import tempfile
from pathlib import Path

from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def test_sharp_install():
    """Install crm to ~/yak/crm/ and verify the structure."""
    root = Path(tempfile.mkdtemp(prefix="yak-sharp-"))
    try:
        repo_root = Path(__file__).resolve().parents[3]
        packs = repo_root / "packs"
        runtime = repo_root / "runtime"
        dists = repo_root / "apps" / "y5n-apps-yak" / "dists"

        repo = FileRepository(packs, runtime, builtin_dists=dists)
        artifacts = DirectoryArtifactStore(packs, runtime)
        mgr = InstallationManager(repo, artifacts)

        inst = mgr.install("crm", root / "installations" / "crm")

        print(f"Name:         {inst.name}")
        print(f"Distribution: {inst.distribution}")
        print(f"Status:       {inst.status.value}")
        print(f"Packs:        {', '.join(inst.packs)}")
        print(f"Root:         {inst.root}")
        print()

        for child in sorted(inst.root.iterdir()):
            suffix = "/" if child.is_dir() else ""
            print(f"  {child.name}{suffix}")

        workspace = inst.root / "workspace.toml"
        assert workspace.exists()
        content = workspace.read_text()
        assert "crm" in content

        state = inst.root / ".yak" / "state.toml"
        assert state.exists()

        print()
        print("Sharp test passed.")
        print()
        print(f"Installation is at: {inst.root}")
        print("It will be deleted when this test finishes.")

    finally:
        shutil.rmtree(root)
