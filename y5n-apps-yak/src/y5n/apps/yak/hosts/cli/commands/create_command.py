from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.generator.command import create_command


def _pack_name_from_root(pack_root: Path) -> str:
    import tomllib

    try:
        with open(pack_root / "pack.toml", "rb") as f:
            return tomllib.load(f).get("name", pack_root.name)
    except Exception:
        return pack_root.name


def run(args, mgr) -> None:
    name = args.name
    pack_name = getattr(args, "pack", None)
    force = getattr(args, "force", False)

    structure_dir = create_command(name, pack_name=pack_name, force=force)
    pack_root = structure_dir.parent.parent
    pname = _pack_name_from_root(pack_root)
    src_file = pack_root / "src" / "y5n" / "packs" / pname / f"{name}.py"
    print(f"\nCommand '{name}' created.\n")
    for p in sorted(structure_dir.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(pack_root)}")
    if src_file.exists():
        print(f"  {src_file.relative_to(pack_root)}")
    print()
    print("Next step: yak build <source>")
