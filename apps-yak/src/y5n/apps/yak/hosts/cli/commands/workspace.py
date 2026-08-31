"""yak workspace — manage Yakoon workspaces."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def run(args, mgr) -> None:
    match args.ws_action:
        case "create":
            _create(args)


def _create(args) -> None:
    name = args.name
    root = Path(name).resolve()

    if root.exists():
        if not root.is_dir():
            print(f"Error: {name} exists and is not a directory")
            raise SystemExit(1)
        if list(root.iterdir()):
            print(f"Error: {name} is not empty")
            raise SystemExit(1)

    ws_parent = _find_workspace_parent(root)
    if ws_parent:
        print(f"Error: {name} is inside an existing Yakoon Workspace ({ws_parent})")
        raise SystemExit(1)

    root.mkdir(parents=True, exist_ok=True)
    (root / "packs").mkdir(exist_ok=True)

    now = datetime.now(UTC).isoformat()
    manifest = f"""\
[workspace]
name = "{name}"
manifest = "1"
created = "{now}"
"""
    (root / "workspace.toml").write_text(manifest)

    print(f"Workspace '{name}' created at {root}")
    print()
    print(f"  cd {name}")
    print("  yak create cap <name>")
    print("  yak shell")


def _find_workspace_parent(path: Path) -> Path | None:
    for parent in [path] + list(path.parents):
        if (parent / "workspace.toml").exists():
            return parent
    return None
