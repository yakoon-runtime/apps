"""yak sync — materialize workspace from environment.yml."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.environment.io import load, save
from y5n.apps.yak.hosts.cli.cwd import find_context_root
from y5n.apps.yak.pack.models import Mount
from y5n.apps.yak.workspace.materializer import Materializer


def run(args, mgr) -> None:
    ctx = find_context_root()
    if ctx is None:
        print("Not inside a Yak context.")
        print("Run 'yak init' first or cd into one.")
        return

    env = load(ctx)

    # First sync: discover local packs and create environment.yml
    if env is None:
        discovered = _discover_mounts(ctx)
        if not discovered:
            print("Nothing to synchronize — no packs or mounts found.")
            return
        from y5n.apps.yak.environment.models import Environment

        env = Environment(name=ctx.name)
        env.mounts = discovered
        save(env, ctx)
        print(f"  Created environment with {len(discovered)} mount(s)")

    # Materialize workspace from mounts
    materializer = Materializer()
    structure_dir = ctx / env.workspace_path
    materializer.materialize(structure_dir, env.name, mounts=list(env.mounts))

    print(f"  Synced {len(env.mounts)} mount(s) → {structure_dir}")


def _discover_mounts(context_root: Path) -> list[Mount]:
    """Scan context root for pack.toml directories and create mounts."""
    mounts: list[Mount] = []

    if not context_root.is_dir():
        return mounts

    if (context_root / "pack.toml").exists():
        src = context_root / "structure"
        if src.is_dir():
            mounts.append(
                Mount(source=str(src.resolve()), target=f"/{context_root.name}")
            )

    for child in sorted(context_root.iterdir()):
        if child.is_dir() and (child / "pack.toml").exists():
            src = child / "structure"
            if src.is_dir():
                mounts.append(Mount(source=str(src.resolve()), target=f"/{child.name}"))
    return mounts
