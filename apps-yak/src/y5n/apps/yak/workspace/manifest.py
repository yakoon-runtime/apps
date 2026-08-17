"""The materialized-workspace manifest (ADR-22).

Records what Yak has materialized into the workspace. This is the
boundary between managed and unmanaged content: Yak may create, change
and remove anything listed here; everything else in the tree is left
untouched.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_NAME = "workspace.toml"


@dataclass
class MaterializedFile:
    """One materialized entry, relative to the mount's target directory.

    ``path`` is relative (POSIX); directories carry no hash. A file's
    hash is the sha256 of its content and is used both to detect changes
    on update and to decide whether Yak may remove it (only if the
    target still matches the recorded hash).
    """

    path: str
    sha256: str = ""
    is_dir: bool = False


@dataclass
class MaterializedMount:
    source: str
    target: str
    files: list[MaterializedFile] = field(default_factory=list)

    def by_path(self) -> dict[str, MaterializedFile]:
        return {f.path: f for f in self.files}


@dataclass
class MaterializedManifest:
    """The managed set of one environment, keyed by mount."""

    created: datetime | None = None
    updated: datetime | None = None
    mounts: list[MaterializedMount] = field(default_factory=list)

    def mount(self, source: str, target: str) -> MaterializedMount | None:
        for m in self.mounts:
            if m.source == source and m.target == target:
                return m
        return None


def read_manifest(root: Path) -> MaterializedManifest | None:
    """Read the manifest from ``<root>/workspace.toml`` if present."""
    path = root / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None
    ws = data.get("workspace", {})
    if ws.get("version") != "2":
        return None
    mounts: list[MaterializedMount] = []
    for raw in data.get("materialized", []):
        files = [
            MaterializedFile(
                path=f.get("path", ""),
                sha256=f.get("sha256", ""),
                is_dir=bool(f.get("dir", False)),
            )
            for f in raw.get("files", [])
        ]
        mounts.append(
            MaterializedMount(
                source=raw.get("source", ""),
                target=raw.get("target", ""),
                files=files,
            )
        )
    return MaterializedManifest(
        created=_parse_dt(ws.get("created")),
        updated=_parse_dt(ws.get("updated")),
        mounts=mounts,
    )


def write_manifest(root: Path, manifest: MaterializedManifest) -> None:
    """Write the manifest as TOML (manually serialized, no extra dep)."""
    now = datetime.now(UTC)
    manifest.updated = now
    lines = [
        "[workspace]",
        'version = "2"',
        f'created = "{_iso(manifest.created or now)}"',
        f'updated = "{now.isoformat()}"',
        "",
    ]
    for mount in manifest.mounts:
        lines.append("[[materialized]]")
        lines.append(f'source = "{_esc(mount.source)}"')
        lines.append(f'target = "{_esc(mount.target)}"')
        for f in mount.files:
            if f.is_dir:
                lines.append("\n[[materialized.files]]")
                lines.append(f'path = "{_esc(f.path)}"')
                lines.append("dir = true")
            else:
                lines.append("\n[[materialized.files]]")
                lines.append(f'path = "{_esc(f.path)}"')
                lines.append(f'sha256 = "{f.sha256}"')
        lines.append("")
    (root / MANIFEST_NAME).write_text("\n".join(lines))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_dt(raw: str | None) -> datetime | None:
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return None
