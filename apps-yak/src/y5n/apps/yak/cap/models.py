from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import NewType

CapName = NewType("CapName", str)


def read_mount(path: Path) -> str | None:
    """Read a component's mount target from mount.toml, if any."""
    manifest = path / "mount.toml"
    if not manifest.exists():
        return None
    try:
        with open(manifest, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None
    value = data.get("path")
    return str(value) if value else None


@dataclass(frozen=True)
class Mount:
    source: str
    target: str


@dataclass(frozen=True)
class Cap:
    """Source component metadata: native identity plus optional mount.

    ``name`` is the component's native identity (its pyproject project
    name); ``mount`` is the tree path the component's structure is
    mounted into (e.g. ``/usr/bin`` for the system cap), declared in
    ``mount.toml``. Versioning belongs to the native build manifest —
    this model never carries it.
    """

    name: str
    mount: str | None = None
