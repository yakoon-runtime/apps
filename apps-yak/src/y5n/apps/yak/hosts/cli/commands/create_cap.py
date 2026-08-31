from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.generator.pack import create_cap


def run(args, mgr) -> None:
    name = args.name
    target = Path(args.target) if args.target else None
    force = getattr(args, "force", False)

    try:
        root = create_cap(name, target=target, force=force)
    except FileExistsError as e:
        print(f"\nError: {e}")
        raise SystemExit(1)

    print(f"\nPack '{name}' created at {root}\n")

    for p in sorted(root.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(root)}")
    print()

    print("Next steps:")
    print(f"  cd {name}")
    print("  yak create command <name>   # add a command")
    print("  cd ..")
    print("  yak build <source>         # build the cap")
    print("  yak update                 # install")
