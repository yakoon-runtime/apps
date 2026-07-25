import tempfile
from pathlib import Path

from y5n.apps.yak.distribution.models import Mount, PackName
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.workspace.materializer import Materializer


def test_materialize_with_mounts():
    with tempfile.TemporaryDirectory() as tmp:
        packs_root = Path(tmp) / "packs"
        ws_root = Path(tmp) / "workspace"

        pack_dir = packs_root / "test-pack" / "structure"
        pack_dir.mkdir(parents=True)
        (pack_dir / "hello.txt").write_text("hi")

        store = DirectoryArtifactStore(packs_root)
        mat = Materializer(store)
        mounts = [Mount(pack=PackName("test-pack"), target="/opt/app")]
        ws = mat.materialize(ws_root, "test", [PackName("test-pack")], mounts=mounts)

        assert ws.path == ws_root
        assert ws.distribution == "test"
        assert ws.packs == [PackName("test-pack")]
        assert ws.created is not None
        assert ws.updated is not None

        manifest = ws_root / "workspace.toml"
        assert manifest.exists()
        assert "test-pack" in manifest.read_text()

        # Structure appears at /opt/app (the mount target)
        link = ws_root / "structure" / "opt" / "app"
        assert link.is_symlink()
        assert (link / "hello.txt").exists()


def test_materialize_at_root():
    with tempfile.TemporaryDirectory() as tmp:
        packs_root = Path(tmp) / "packs"
        ws_root = Path(tmp) / "workspace"

        pack_dir = packs_root / "test-pack" / "structure"
        pack_dir.mkdir(parents=True)
        (pack_dir / "_yak").mkdir()
        (pack_dir / "hello.txt").write_text("hi")

        store = DirectoryArtifactStore(packs_root)
        mat = Materializer(store)
        mounts = [Mount(pack=PackName("test-pack"), target="/")]
        ws = mat.materialize(ws_root, "test", [PackName("test-pack")], mounts=mounts)

        link = ws_root / "structure" / "_yak"
        assert link.is_symlink()

        link2 = ws_root / "structure" / "hello.txt"
        assert link2.is_symlink()
