from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path


def run(args, mgr) -> None:
    path = _resolve_path(args)
    if path is None:
        print("Not inside a Yak installation.")
        print("Use --path <dir> or cd into an installation directory.")
        return

    inst = mgr.load(path)
    if inst is None:
        print("Not a valid Yak installation.")
        return

    _show(inst)


def _resolve_path(args) -> Path | None:
    if hasattr(args, "path") and args.path:
        return Path(args.path).resolve()
    return find_installation_path()


def _show(inst) -> None:
    print(f"  {inst.name}")
    print(f"    distribution: {inst.distribution}")
    print(f"    status: {inst.status.value}")
    print(f"    packs: {', '.join(inst.packs)}")
