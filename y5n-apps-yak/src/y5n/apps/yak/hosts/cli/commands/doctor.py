from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI()
    target = args.target
    if target and target != ".":
        path = Path(target).resolve()
    else:
        path = find_installation_path()

    if path is None:
        ui.fail("No installation specified. cd into one or pass a directory.")
        return

    issues = ui.task("Doctor", lambda: mgr.doctor(path))
    name = path.name
    if not issues:
        ui.ok(f"{name}: healthy")
        return
    print(f"{name}: {len(issues)} issue(s)")
    for issue in issues:
        print(f"  - {issue}")
