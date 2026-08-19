from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NewType

import yaml

CapName = NewType("CapName", str)


class MountError(Exception):
    """A .yak/mount.yml violates the component delivery contract."""


@dataclass(frozen=True)
class ComponentMount:
    """A component's delivery declaration (mount.yml): source → path.

    ``source`` is a path relative to the component root whose content is
    mounted; ``path`` is its target in the materialized tree. Both are
    mandatory: a mount.yml that exists declares the complete mapping.
    """

    source: str
    target: str


def read_mount(path: Path) -> ComponentMount | None:
    """Read a component's delivery declaration from .yak/mount.yml, if any.

    No mount.yml means the component delivers nothing into the tree. A
    mount.yml that exists must declare both ``source`` (component-relative
    path) and ``path`` (tree target) — the component layout is otherwise
    free (no ``structure`` magic anywhere).
    """
    manifest = path / ".yak" / "mount.yml"
    if not manifest.exists():
        return None
    try:
        data = yaml.safe_load(manifest.read_text()) or {}
    except Exception as exc:
        raise MountError(f"cannot read {manifest}: {exc}") from exc
    if not isinstance(data, dict):
        raise MountError(f"{manifest} must be a mapping")
    source = data.get("source")
    target = data.get("path")
    if not isinstance(source, str) or not source:
        raise MountError(f"{manifest} needs a 'source' (component-relative path)")
    if not isinstance(target, str) or not target:
        raise MountError(f"{manifest} needs a 'path' (tree target)")
    return ComponentMount(source=source, target=target)


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
    """Source component metadata: identity plus optional delivery.

    ``name`` and ``version`` are the component's Yakoon identity,
    declared in ``.yak/component.yml`` (ADR-23); ``mount`` is the delivery
    declaration (source → path), if any, from ``.yak/mount.yml``.
    """

    name: str
    version: str
    mount: ComponentMount | None = None
