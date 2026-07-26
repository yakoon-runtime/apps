"""yak doctor — check installation health."""

from __future__ import annotations

from y5n.apps.yak.hosts.cli.cwd import find_installation_path
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    path = find_installation_path()
    if path is None:
        print("Not inside a Yak installation.")
        print("Run 'yak install' first or cd into one.")
        return

    ui = TerminalUI()
    issues = ui.task("Doctor", lambda: mgr.doctor(path))
    name = path.name
    if not issues:
        print(f"  {name}: healthy")
        return
    print(f"  {name}: {len(issues)} issue(s)")
    for issue in issues:
        print(f"    - {issue}")
