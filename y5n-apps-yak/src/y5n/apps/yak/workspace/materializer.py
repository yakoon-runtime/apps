from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from y5n.apps.yak.distribution.models import Mount
from y5n.apps.yak.workspace.models import Workspace


class Materializer:
    def __init__(self) -> None:
        pass

    def materialize(
        self,
        structure_dir: Path,
        distribution: str,
        mounts: list[Mount] | None = None,
    ) -> Workspace:
        structure_dir.mkdir(parents=True, exist_ok=True)

        mounts = mounts or []
        for mount in mounts:
            source = Path(mount.source)
            if not source.is_dir():
                continue

            if mount.target == "/":
                for child in sorted(source.iterdir()):
                    dst = structure_dir / child.name
                    if not dst.exists():
                        dst.symlink_to(
                            child.resolve(), target_is_directory=child.is_dir()
                        )
            else:
                target = structure_dir / mount.target.strip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.symlink_to(source.resolve(), target_is_directory=True)

        now = datetime.now(timezone.utc)

        workspace_root = structure_dir.parent
        self._write_manifest(workspace_root, distribution, now)

        return Workspace(
            path=workspace_root,
            distribution=distribution,
            created=now,
            updated=now,
        )

    def _write_manifest(
        self,
        root: Path,
        distribution: str,
        now: datetime,
    ) -> None:
        manifest = f"""\
[workspace]
distribution = "{distribution}"
version = "1"
created = "{now.isoformat()}"
updated = "{now.isoformat()}"
"""
        with open(root / "workspace.toml", "w") as f:
            f.write(manifest)
