"""yak init — create a Yak context in the current directory."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def run(args, mgr) -> None:
    target = Path(args.target).resolve() if args.target else Path.cwd().resolve()
    _init(target)


def _init(root: Path) -> None:
    if (root / ".yak").exists():
        print(f"Error: {root} is already a Yak context")
        return

    root.mkdir(parents=True, exist_ok=True)

    yak_dir = root / ".yak"
    yak_dir.mkdir(exist_ok=True)

    now = datetime.now(UTC).isoformat()
    ctx = f"""\
[context]
name = "{root.name}"
created = "{now}"
"""
    (yak_dir / "context.toml").write_text(ctx)

    print(f"Yak context created at {root}")
