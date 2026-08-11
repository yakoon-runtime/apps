"""yak mount — manage workspace mounts."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.environment.io import load, save
from y5n.apps.yak.hosts.cli.cwd import find_context_root
from y5n.apps.yak.pack.models import Mount
from y5n.apps.yak.workspace.materializer import Materializer


def run_add(args, mgr) -> None:
    ctx = find_context_root()
    if ctx is None:
        print("Not inside a Yak context.")
        print("Run 'yak init' first or cd into one.")
        return

    env = load(ctx)
    if env is None:
        print("No .yak/environment.yml found. Run 'yak install' first.")
        return

    source = Path(args.source).resolve()
    if not source.is_dir():
        print(f"  ✘ Source not found: {source}")
        return

    _warn_large_mount(source)

    target = args.target or f"/{source.name}"
    mount = Mount(source=str(source), target=target)

    if mount in env.mounts:
        print(f"  ✓ Mount already exists: {target} ← {source}")
        return

    env.mounts.append(mount)
    save(env, ctx)

    materializer = Materializer()
    structure_dir = ctx / env.workspace_path
    materializer.materialize(structure_dir, env.name, mounts=list(env.mounts))

    print(f"  ✓ Mount added: {target} ← {source}")


def run_remove(args, mgr) -> None:
    ctx = find_context_root()
    if ctx is None:
        print("Not inside a Yak context.")
        return

    env = load(ctx)
    if env is None:
        return

    target = args.target
    before = len(env.mounts)
    env.mounts = [m for m in env.mounts if m.target != target]

    if len(env.mounts) == before:
        print(f"  — No mount found at: {target}")
        return

    save(env, ctx)

    materializer = Materializer()
    structure_dir = ctx / env.workspace_path
    materializer.materialize(structure_dir, env.name, mounts=list(env.mounts))

    print(f"  ✓ Mount removed: {target}")


def run_list(args, mgr) -> None:
    ctx = find_context_root()
    if ctx is None:
        print("Not inside a Yak context.")
        return

    env = load(ctx)
    if env is None or not env.mounts:
        print("  No mounts configured.")
        return

    print(f"  Mounts ({len(env.mounts)}):")
    for m in env.mounts:
        print(f"    {m.target} ← {m.source}")


def _warn_large_mount(path: Path, limit: int = 5000) -> None:
    """Warn if the source directory has too many entries (scanner safety)."""
    count = 0
    try:
        for _ in path.iterdir():
            count += 1
            if count > limit:
                print(
                    f"  ⚠  {path} has over {limit} entries —"
                    " this may slow down the workspace scanner"
                )
                return
    except PermissionError:
        print(f"  ⚠  Permission denied: {path}")
