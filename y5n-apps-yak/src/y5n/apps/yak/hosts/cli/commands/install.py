"""yak install <component|bundle> [--target <dir>] — compose an environment.

The first argument is always an identity: a component name or a bundle
name. On a fresh environment the identity is materialized; on an
existing environment its components are added. Every component resolves
through its release.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    root = Path(getattr(args, "target", ".")).resolve()
    identity = args.identity

    _ensure_context(root)

    ui.title(f'Installing "{identity}"')
    try:
        mgr.install(root, ui=ui, identity=identity)
        ui.ok(f"Installed {identity}")
    except Exception as e:
        ui.fail(f"Installation failed: {e}")


def _ensure_context(root: Path) -> None:
    """Create the context (bootstrap → .yak/context.toml) if it is missing.

    The context carries the sources; without it no later command (add,
    update, shell) can resolve anything. Creating it is a no-op when the
    target already sits inside a context.
    """
    ctx_file = root / ".yak" / "context.toml"
    if ctx_file.exists():
        return
    from y5n.apps.yak.hosts.cli.commands import init_cmd

    init_cmd._init(root)
