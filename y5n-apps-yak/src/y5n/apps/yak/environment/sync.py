"""Sync .yak/environment.yml — add mounts for newly installed packs."""

from __future__ import annotations

from y5n.apps.yak.pack.models import Mount

from .models import Environment


def add_mount(env: Environment, source: str, target: str) -> Mount:
    """Add a mount. Returns the mount (existing or new)."""
    for m in env.mounts:
        if m.source == source and m.target == target:
            return m
    mount = Mount(source=source, target=target)
    env.mounts.append(mount)
    return mount
