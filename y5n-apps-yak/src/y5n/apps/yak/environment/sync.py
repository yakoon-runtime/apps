"""Sync .yak/environment.yml — add mounts for newly installed packs."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.distribution.models import Mount, PackName

from .io import load, save
from .models import Environment


def add_mount(env: Environment, pack_name: PackName) -> Mount:
    """Add a default mount for a pack. Returns the mount (existing or new)."""
    for m in env.mounts:
        if m.pack == pack_name:
            return m
    mount = Mount(pack=pack_name, target=f"/{pack_name}")
    env.mounts.append(mount)
    return mount


def sync(context_root: Path, installed_packs: list[PackName]) -> Environment:
    """Sync environment: add default mounts for installed packs that have none."""
    env = load(context_root)
    if env is None:
        raise RuntimeError(f"no environment found at {context_root}/.yak/")

    for pack in installed_packs:
        add_mount(env, pack)

    save(env, context_root)
    return env
