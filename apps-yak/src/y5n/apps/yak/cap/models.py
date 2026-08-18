from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NewType

import yaml

CapName = NewType("CapName", str)


def read_mount(path: Path) -> str | None:
    """Read a component's mount target from .yak/mount.yml, if any.

    The mount is part of the component-local Yakoon contract (ADR-23);
    the manifest is YAML (``path: /usr/bin``).
    """
    manifest = path / ".yak" / "mount.yml"
    if not manifest.exists():
        return None
    try:
        data = yaml.safe_load(manifest.read_text()) or {}
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
    ``.yak/mount.yml``. Versioning belongs to the native build manifest —
    this model never carries it.
    """

    name: str
    mount: str | None = None
