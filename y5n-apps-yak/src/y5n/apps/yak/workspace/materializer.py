from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from y5n.apps.yak.pack.models import Mount
from y5n.apps.yak.workspace.models import Workspace


class Materializer:
    """Compose the workspace tree from mount sources.

    The workspace is a pure composition of symlinks. Mount sources must
    be staged component paths (``.yak/components/<name>/structure``) or
    explicit operator paths — never artifact stores or language
    packages. Sources are referenced with ``absolute()`` (not
    ``resolve()``) so the workspace points at the staged component path,
    keeping the source-of-truth boundary intact.
    """

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
        if components_dir is not None:
            self._prune(structure_dir, sources, components_dir)

        for mount in mounts:
            source = Path(mount.source)
            if not source.is_dir():
                continue

            if mount.target == "/":
                for child in sorted(source.iterdir()):
                    dst = structure_dir / child.name
                    if not dst.exists():
                        dst.symlink_to(
                            child.absolute(), target_is_directory=child.is_dir()
                        )
            else:
                target = structure_dir / mount.target.strip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.symlink_to(source.absolute(), target_is_directory=True)

        now = datetime.now(timezone.utc)

        workspace_root = structure_dir.parent
        self._write_manifest(workspace_root, now)

        return Workspace(path=workspace_root, created=now, updated=now)

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

    @classmethod
    def _prune(
        cls,
        structure_dir: Path,
        sources: list[Path],
        components_dir: Path,
    ) -> None:
        """Remove stale component symlinks from the workspace.

        A symlink pointing into the component store whose target is no
        longer covered by a current mount source is a leftover of a
        removed component — it is deleted. Real directories and non-
        component symlinks are left untouched.
        """
        if not structure_dir.is_dir():
            return
        norm_components = os.path.normpath(components_dir.absolute())
        for entry in list(structure_dir.rglob("*")):
            if not entry.is_symlink():
                continue
            try:
                target = entry.readlink()
            except OSError:
                continue
            if not target.is_absolute():
                target = structure_dir / target
            norm_target = os.path.normpath(target.absolute())
            if (
                not norm_target.startswith(norm_components + os.sep)
                and norm_target != norm_components
            ):
                continue
            if cls._covered_by_sources(norm_target, sources):
                continue
            entry.unlink()

    @staticmethod
    def _covered_by_sources(target: str, sources: list[Path]) -> bool:
        for source in sources:
            norm = os.path.normpath(source)
            if target == norm or target.startswith(norm + os.sep):
                return True
        return False

    def _write_manifest(self, root: Path, now: datetime) -> None:
        manifest = f"""\
[workspace]
version = "1"
created = "{now.isoformat()}"
updated = "{now.isoformat()}"
"""
        with open(root / "workspace.toml", "w") as f:
            f.write(manifest)
