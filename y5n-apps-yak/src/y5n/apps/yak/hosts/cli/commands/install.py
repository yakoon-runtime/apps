"""yak install [--target <dir>] — create the minimal Yakoon platform.

The platform is the runtime, the SDK and the host apps — no packs.
Capabilities are composed afterwards with `yak add`.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    root = Path(getattr(args, "target", ".")).resolve()

    if _is_installed(root):
        ui.fail("Yakoon is already installed here — use 'yak add' or 'yak update'")
        return

    _ensure_context(root)

    ui.title("Installing Yakoon")
    try:
        mgr.install(root, ui=ui)
        ui.ok(f"Yakoon ready at {root}")
        ui.detail("Capabilities are added with 'yak add' (e.g. 'yak add system').")
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


def _is_installed(root: Path) -> bool:
    """An installation marker (.yak/state.toml or environment.yml) exists."""
    yak = root / ".yak"
    return (yak / "state.toml").exists() or (yak / "environment.yml").exists()
