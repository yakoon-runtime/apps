"""Materialize the workspace tree (ADR-22).

``.yak/structure`` is a **real** tree: directories, files and ordinary
symlinks. Mount sources are staged component paths
(``.yak/components/<name>/structure``); their content is copied, not
linked. ``caps-root`` provides the base (``mount.target == "/"``), all
other components are overlaid onto it.

The materialized set is recorded in the workspace manifest
(``workspace.toml``). Yak may create, change and remove anything it has
materialized; everything else in the tree is left untouched.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from y5n.apps.yak.cap.models import Mount
from y5n.apps.yak.workspace.manifest import (
    MaterializedFile,
    MaterializedManifest,
    MaterializedMount,
    read_manifest,
    write_manifest,
)
from y5n.apps.yak.workspace.models import Workspace


class Materializer:
    """Compose the workspace tree as a real, materialized structure."""

    def materialize(
        self,
        structure_dir: Path,
        mounts: list[Mount] | None = None,
        *,
        components_dir: Path | None = None,
    ) -> Workspace:
        structure_dir.mkdir(parents=True, exist_ok=True)

        mounts = mounts or []
        sources = [Path(m.source).absolute() for m in mounts]
        self._validate_sources(sources)

        old = read_manifest(structure_dir.parent)
        new = MaterializedManifest(created=(old.created if old else datetime.now(UTC)))

        ordered = self._order_mounts(mounts)
        for mount in ordered:
            source = Path(mount.source)
            if not source.is_dir():
                continue
            target_dir = (
                structure_dir
                if mount.target == "/"
                else structure_dir / mount.target.strip("/")
            )
            # The mount target itself may be a pre-ADR-22 symlink into the
            # component store (old materializer linked at the target).
            if target_dir.is_symlink() and self._is_legacy_yak_link(
                target_dir, structure_dir, components_dir
            ):
                target_dir.unlink()
            entries = self._reconcile(source, target_dir, mount, old, components_dir)
            new.mounts.append(
                MaterializedMount(
                    source=str(source.absolute()),
                    target=mount.target,
                    files=entries,
                )
            )

        self._remove_stale_mounts(structure_dir, ordered, old)

        write_manifest(structure_dir.parent, new)

        workspace_root = structure_dir.parent
        return Workspace(
            path=workspace_root,
            created=new.created or datetime.now(UTC),
            updated=datetime.now(UTC),
        )

    @staticmethod
    def _order_mounts(mounts: list[Mount]) -> list[Mount]:
        """The base mount first, then the overlays in declared order."""
        return sorted(mounts, key=lambda m: (m.target != "/"))

    def _reconcile(
        self,
        source: Path,
        target_dir: Path,
        mount: Mount,
        old: MaterializedManifest | None,
        components_dir: Path | None,
    ) -> list[MaterializedFile]:
        """Bring ``target_dir`` in sync with ``source``.

        Returns the managed entries of this mount. Entries already
        materialized (in the old manifest) may be created, changed or
        removed; anything else in the target tree is left untouched.
        """
        old_entries = {}
        if old is not None:
            prior = old.mount(str(source.absolute()), mount.target)
            if prior is not None:
                old_entries = prior.by_path()
        current = self._walk(source)
        result: list[MaterializedFile] = []

        for rel in sorted(current):
            src = current[rel]
            dst = target_dir / rel
            managed_before = rel in old_entries

            if dst.is_symlink() and self._is_legacy_yak_link(
                dst, target_dir, components_dir
            ):
                # Old symlink materialization (pre ADR-22): replace it.
                dst.unlink()

            if src.is_symlink():
                if managed_before and self._file_changed(src, old_entries[rel]):
                    self._copy_symlink(src, dst)
                elif not dst.exists():
                    self._copy_symlink(src, dst)
                result.append(self._record(src, rel))
                continue

            if src.is_dir():
                if not dst.exists():
                    dst.mkdir(parents=True, exist_ok=True)
                    result.append(MaterializedFile(path=rel, is_dir=True))
                elif managed_before:
                    result.append(MaterializedFile(path=rel, is_dir=True))
                # else: unmanaged directory in the way — leave untouched.
                continue

            # Regular file.
            if managed_before and self._file_changed(src, old_entries[rel]):
                if dst.is_dir() and dst.exists():
                    shutil.rmtree(dst)
                elif dst.is_symlink() and dst.exists():
                    dst.unlink()
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                result.append(self._record(src, rel))
            elif not dst.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                result.append(self._record(src, rel))
            elif managed_before:
                # Unchanged managed file.
                result.append(self._record(src, rel))
            # else: unmanaged file in the way — leave untouched.

        # Remove stale managed entries (deepest first) that the source
        # no longer contains. A managed directory is removed only when it
        # is empty afterwards — user content inside keeps it alive.
        for rel in sorted(old_entries, key=lambda p: p.count("/"), reverse=True):
            if rel in current:
                continue
            dst = target_dir / rel
            if dst.is_symlink() or dst.is_file():
                dst.unlink(missing_ok=True)
            elif dst.is_dir():
                try:
                    dst.rmdir()
                except OSError:
                    pass

        # Keep deterministic order in the manifest.
        return sorted(result, key=lambda f: f.path)

    @staticmethod
    def _remove_stale_mounts(
        structure_dir: Path,
        mounts: list[Mount],
        old: MaterializedManifest | None,
    ) -> None:
        """Remove managed entries of mounts that no longer exist."""
        if old is None:
            return
        active = {(m.source, m.target) for m in mounts}
        for mount in old.mounts:
            if (mount.source, mount.target) in active:
                continue
            for entry in sorted(
                mount.files, key=lambda f: f.path.count("/"), reverse=True
            ):
                dst = structure_dir / mount.target.strip("/") / entry.path
                if entry.is_dir:
                    try:
                        dst.rmdir()
                    except OSError:
                        pass
                else:
                    if dst.is_symlink() or dst.is_file():
                        dst.unlink(missing_ok=True)

    # ── Helpers ──

    @staticmethod
    def _walk(source: Path) -> dict[str, Path]:
        """Relative paths of all entries under ``source`` (no link follow)."""
        result: dict[str, Path] = {}
        for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
            dirnames.sort()
            base = Path(dirpath)
            for name in dirnames:
                result[(base / name).relative_to(source).as_posix()] = base / name
            for name in filenames:
                p = base / name
                result[p.relative_to(source).as_posix()] = p
        return result

    @staticmethod
    def _file_changed(src: Path, old_entry: MaterializedFile | None) -> bool:
        if old_entry is None:
            return True
        if old_entry.is_dir or src.is_dir():
            return False
        return Materializer._sha256(src) != old_entry.sha256

    @staticmethod
    def _record(src: Path, rel: str) -> MaterializedFile:
        if src.is_dir():
            return MaterializedFile(path=rel, is_dir=True)
        if src.is_symlink():
            return MaterializedFile(path=rel, sha256=os.readlink(src))
        return MaterializedFile(path=rel, sha256=Materializer._sha256(src))

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _copy_symlink(src: Path, dst: Path) -> None:
        if dst.is_symlink() or dst.is_file():
            dst.unlink(missing_ok=True)
        elif dst.is_dir():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(os.readlink(src), target_is_directory=src.is_dir())

    @staticmethod
    def _is_legacy_yak_link(
        dst: Path, structure_dir: Path, components_dir: Path | None
    ) -> bool:
        """True for a symlink pointing into the component store.

        Pre-ADR-22 workspaces mounted components by symlinking them into
        the tree. Such links are Yak-owned and may be replaced by real
        content during migration.
        """
        if components_dir is None or not dst.is_symlink():
            return False
        try:
            target = dst.readlink()
        except OSError:
            return False
        if not target.is_absolute():
            target = structure_dir / target
        return os.path.normpath(target.absolute()) == os.path.normpath(
            components_dir.absolute()
        ) or os.path.normpath(target.absolute()).startswith(
            os.path.normpath(components_dir.absolute()) + os.sep
        )

    @classmethod
    def _validate_sources(cls, sources: list[Path]) -> None:
        """Refuse artifact stores and language packages as mount sources."""
        for source in sources:
            if cls._is_store_or_package(source):
                raise ValueError(
                    "Refusing mount source inside an artifact store or a "
                    f"language package: {source}\n"
                    "Stage the component into .yak/components/ first."
                )

    @staticmethod
    def _is_store_or_package(path: Path) -> bool:
        parts = path.absolute().parts
        if "site-packages" in parts or "dist-packages" in parts:
            return True
        for i, part in enumerate(parts):
            if part == ".yak" and i + 1 < len(parts) and parts[i + 1] == "artifacts":
                return True
        return False
