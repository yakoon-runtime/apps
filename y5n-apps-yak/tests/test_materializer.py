import tempfile
from pathlib import Path

from y5n.apps.yak.pack.models import Mount
from y5n.apps.yak.workspace.materializer import Materializer


def test_materialize_with_mounts():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / "hello.txt").write_text("hi")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/opt/app")]
        ws = mat.materialize(structure_dir, "test", mounts=mounts)

        assert ws.path == structure_dir.parent
        assert ws.distribution == "test"
        assert ws.created is not None
        assert ws.updated is not None

        # Structure appears at /opt/app (the mount target)
        link = structure_dir / "opt" / "app"
        assert link.is_symlink()
        assert (link / "hello.txt").exists()


def test_materialize_at_root():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / ".yak").mkdir()
        (source_dir / "hello.txt").write_text("hi")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/")]
        ws = mat.materialize(structure_dir, "test", mounts=mounts)

        link = structure_dir / ".yak"
        assert link.is_symlink()

        link2 = structure_dir / "hello.txt"
        assert link2.is_symlink()
