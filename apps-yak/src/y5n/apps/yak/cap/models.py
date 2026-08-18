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


def cap_from_data(data) -> "Cap | None":
    """Build a Cap from parsed component.yml content, if it declares an identity.

    ``name`` declares *who a component is*, ``version`` *which version* —
    both are mandatory (ADR-23). The mount is not part of component.yml
    and is read separately by ``read_component``.
    """
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    version = data.get("version")
    if not name or not version:
        return None
    return Cap(name=str(name), version=str(version))


def read_component(path: Path) -> "Cap | None":
    """Read a component's identity from .yak/component.yml, if any.

    ``.yak/component.yml`` is the authoritative identity of a component
    (ADR-23). The manifest is YAML (``name: y5n-caps-system`` /
    ``version: 0.8.0``); the mount, if any, is read from .yak/mount.yml.
    """
    manifest = path / ".yak" / "component.yml"
    if not manifest.exists():
        return None
    try:
        data = yaml.safe_load(manifest.read_text()) or {}
    except Exception:
        return None
    cap = cap_from_data(data)
    if cap is None:
        return None
    return Cap(name=cap.name, version=cap.version, mount=read_mount(path))


@dataclass(frozen=True)
class Mount:
    source: str
    target: str


@dataclass(frozen=True)
class Cap:
    """Source component metadata: identity plus optional mount.

    ``name`` and ``version`` are the component's Yakoon identity,
    declared in ``.yak/component.yml`` (ADR-23); ``mount`` is the tree
    path the component's structure is mounted into (e.g. ``/usr/bin``
    for the system cap), declared in ``.yak/mount.yml``.
    """

    name: str
    version: str
    mount: str | None = None
