"""yak status — show context status."""

from __future__ import annotations

from y5n.apps.yak.environment.io import load as load_env
from y5n.apps.yak.hosts.cli.cwd import find_context_root


def run(args, mgr) -> None:
    ctx = find_context_root()
    if ctx is None:
        print("Not inside a Yak context.")
        return

    print(f"  Context: {ctx.name} ({ctx})")

    env = load_env(ctx)
    if env is None:
        print("  Environment: none")
        print("  Run 'yak install <component|bundle>' (e.g. 'yak install runtime')")
        return

    print(f"  Environment: {env.name}")
    print(f"  Workspace:   {ctx / env.workspace_path}")
    print(f"  Mounts:      {len(env.mounts)}")
    for m in env.mounts:
        print(f"    {m.target} ← {m.source}")
