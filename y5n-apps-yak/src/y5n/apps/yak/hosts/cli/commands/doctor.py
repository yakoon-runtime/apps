"""yak doctor — check installation health."""

from __future__ import annotations

from y5n.apps.yak.hosts.cli.cwd import find_installation_path
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    from y5n.apps.yak.hosts.cli.cwd import find_context_root

    # Show context info regardless of installation
    ctx = find_context_root()
    if ctx:
        print(f"  Context: {ctx}")

    path = find_installation_path()
    if path is None:
        print("  Not inside a Yak installation.")
        print("  Run 'yak install' first or cd into one.")
        return

    results = mgr.doctor(path)
    errors = [r for r in results if r.startswith("✘")]
    for line in results:
        print(f"  {line}")
    if errors:
        print(f"\n  {len(errors)} issue(s) found")
    else:
        print("\n  ✓ Context is consistent")
