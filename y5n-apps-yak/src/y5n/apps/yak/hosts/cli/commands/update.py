"""yak update [<target>] — reconcile the installation with its desired state."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_runtime_root
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))

    target = Path(getattr(args, "target", ".")).resolve()
    if not (target / ".yak" / "state.toml").exists():
        found = find_runtime_root()
        if found is None:
            ui.fail("No installation found — run 'yak install <environment>' first")
            return
        target = found

    try:
        mgr.update(target, ui=ui)
        ui.ok(f"Updated {target}")
    except Exception as e:
        ui.fail(f"Update failed: {e}")
