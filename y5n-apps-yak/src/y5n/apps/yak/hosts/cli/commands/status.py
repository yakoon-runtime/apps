"""yak status — show installation status."""

from __future__ import annotations

from y5n.apps.yak.hosts.cli.cwd import find_installation_path
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    path = find_installation_path()
    if path is None:
        print("Not inside a Yak installation.")
        print("Run 'yak install' first or cd into one.")
        return

    inst = mgr.load(path)
    if inst is None:
        print("Not a valid Yak installation.")
        return

    print(f"  {inst.name}")
    print(f"    distribution: {inst.distribution}")
    print(f"    status: {inst.status.value}")
    print(f"    packs: {', '.join(inst.packs)}")
