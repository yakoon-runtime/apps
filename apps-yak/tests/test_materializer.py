import tempfile
from pathlib import Path

from y5n.apps.yak.cap.models import Mount
from y5n.apps.yak.workspace.materializer import Materializer
from y5n.apps.yak.workspace.manifest import read_manifest


def test_materialize_with_mounts():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / "hello.txt").write_text("hi")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/opt/app")]
        ws = mat.materialize(structure_dir, mounts=mounts)

        assert ws.path == structure_dir.parent
        assert ws.created is not None
        assert ws.updated is not None

        # Structure appears at /opt/app (the mount target) as real content
        target = structure_dir / "opt" / "app"
        assert target.is_dir() and not target.is_symlink()
        assert (target / "hello.txt").exists()
        assert (target / "hello.txt").read_text() == "hi"

        # The managed set is recorded in the manifest.
        manifest = read_manifest(structure_dir.parent)
        assert manifest is not None
        assert len(manifest.mounts) == 1
        assert manifest.mounts[0].target == "/opt/app"
        paths = [f.path for f in manifest.mounts[0].files]
        assert "hello.txt" in paths


def test_materialize_at_root():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / ".yak").mkdir()
        (source_dir / "hello.txt").write_text("hi")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/")]
        ws = mat.materialize(structure_dir, mounts=mounts)

        root = structure_dir
        assert (root / ".yak").is_dir() and not (root / ".yak").is_symlink()
        assert (root / "hello.txt").is_file()
        assert (root / "hello.txt").read_text() == "hi"


def test_base_then_overlay():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base" / "structure"
        base.mkdir(parents=True)
        (base / "usr").mkdir()
        (base / "usr" / "base.txt").write_text("base")

        overlay = Path(tmp) / "overlay" / "structure"
        overlay.mkdir(parents=True)
        (overlay / "cmd.txt").write_text("cmd")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [
            Mount(source=str(base.resolve()), target="/"),
            Mount(source=str(overlay.resolve()), target="/usr/bin"),
        ]
        mat.materialize(structure_dir, mounts=mounts)

        # Base content is present; overlay content lands in /usr/bin.
        assert (structure_dir / "usr" / "base.txt").exists()
        bin_dir = structure_dir / "usr" / "bin"
        assert (bin_dir / "cmd.txt").exists()
        assert not (bin_dir / "cmd.txt").is_symlink()


def test_update_replaces_changed_managed_file():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / "hello.txt").write_text("v1")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/opt/app")]
        mat.materialize(structure_dir, mounts=mounts)

        # Update the source, re-materialize: managed file is replaced.
        (source_dir / "hello.txt").write_text("v2")
        mat.materialize(structure_dir, mounts=mounts)
        assert (structure_dir / "opt" / "app" / "hello.txt").read_text() == "v2"


def test_update_preserves_unmanaged_content():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / "hello.txt").write_text("v1")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/opt/app")]
        mat.materialize(structure_dir, mounts=mounts)

        # A user file inside the tree must survive updates untouched.
        user_file = structure_dir / "opt" / "app" / "mine.txt"
        user_file.write_text("mine")
        user_file.touch()

        (source_dir / "hello.txt").write_text("v2")
        mat.materialize(structure_dir, mounts=mounts)

        assert user_file.exists()
        assert user_file.read_text() == "mine"
        assert (structure_dir / "opt" / "app" / "hello.txt").read_text() == "v2"


def test_update_removes_managed_entry_removed_from_source():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / "keep.txt").write_text("keep")
        (source_dir / "gone.txt").write_text("gone")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/opt/app")]
        mat.materialize(structure_dir, mounts=mounts)

        assert (structure_dir / "opt" / "app" / "gone.txt").exists()

        # Remove a managed file from the source: it must disappear.
        (source_dir / "gone.txt").unlink()
        mat.materialize(structure_dir, mounts=mounts)

        assert not (structure_dir / "opt" / "app" / "gone.txt").exists()
        assert (structure_dir / "opt" / "app" / "keep.txt").exists()


def test_removed_mount_cleans_up():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / "hello.txt").write_text("hi")

        structure_dir = Path(tmp) / "workspace" / "structure"
        mat = Materializer()
        mounts = [Mount(source=str(source_dir.resolve()), target="/opt/app")]
        mat.materialize(structure_dir, mounts=mounts)

        # Removing the mount removes the materialized content.
        mat.materialize(structure_dir, mounts=[])
        assert not (structure_dir / "opt" / "app" / "hello.txt").exists()


def test_legacy_symlink_is_replaced():
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / "my-pack" / "structure"
        source_dir.mkdir(parents=True)
        (source_dir / "hello.txt").write_text("hi")

        components_dir = Path(tmp) / ".yak" / "components"
        staged = components_dir / "my-pack" / "structure"
        staged.parent.mkdir(parents=True)
        staged.symlink_to(source_dir.resolve(), target_is_directory=True)

        structure_dir = Path(tmp) / "workspace" / "structure"
        structure_dir.mkdir(parents=True)
        (structure_dir / "opt").mkdir()
        (structure_dir / "opt" / "app").symlink_to(
            staged, target_is_directory=True
        )

        mat = Materializer()
        mounts = [
            Mount(source=str(staged), target="/opt/app"),
        ]
        mat.materialize(
            structure_dir, mounts=mounts, components_dir=components_dir
        )

        assert not (structure_dir / "opt" / "app").is_symlink()
        assert (structure_dir / "opt" / "app").is_dir()
        assert (structure_dir / "opt" / "app" / "hello.txt").read_text() == "hi"
