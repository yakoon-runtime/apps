from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.generator.command import create_command


def _cap_name_from_root(cap_root: Path) -> str:
    import tomllib

    try:
        with open(cap_root / "pyproject.toml", "rb") as f:
            project = tomllib.load(f).get("project", {})
        return project.get("name", cap_root.name)
    except Exception:
        return cap_root.name


def run(args, mgr) -> None:
    name = args.name
    cap_name = getattr(args, "cap", None)
    force = getattr(args, "force", False)

    try:
        structure_dir = create_command(name, cap_name=cap_name, force=force)
    except (FileExistsError, RuntimeError) as e:
        print(f"\nError: {e}")
        raise SystemExit(1)

    cap_root = structure_dir.parent.parent
    pname = _cap_name_from_root(cap_root)
    src_file = cap_root / "src" / "y5n" / "caps" / pname / f"{name}.py"
    print(f"\nCommand '{name}' created.\n")
    for p in sorted(structure_dir.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(cap_root)}")
    if src_file.exists():
        print(f"  {src_file.relative_to(cap_root)}")
    print()
    print("Next step: yak build <source>")
