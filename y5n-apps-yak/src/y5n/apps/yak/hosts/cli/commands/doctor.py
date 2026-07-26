from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path


def run(args, mgr) -> None:
    path = args.target or find_installation_path()
    if path is None:
        print("No installation specified. cd into one or pass a directory.")
        return

    issues = mgr.doctor(path)
    name = path.name
    if not issues:
        print(f"{name}: healthy")
        return
    print(f"{name}: {len(issues)} issue(s)")
    for issue in issues:
        print(f"  - {issue}")
