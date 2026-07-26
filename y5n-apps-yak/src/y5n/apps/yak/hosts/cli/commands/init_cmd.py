"""yak init — create a Yak context in the current directory."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def run(args, mgr) -> None:
    target = Path(args.target).resolve() if args.target else Path.cwd().resolve()
    _init(target)


def _init(root: Path) -> None:
    yak_dir = root / ".yak"
    already = yak_dir.exists()

    root.mkdir(parents=True, exist_ok=True)
    yak_dir.mkdir(exist_ok=True)

    now = datetime.now(UTC).isoformat()
    (yak_dir / "logs").mkdir(exist_ok=True)

    ctx = f"""\
[context]
name = "{root.name}"
created = "{now}"

[logs]
path = ".yak/logs"
"""
    (yak_dir / "context.toml").write_text(ctx)

    if already:
        print(f"Reinitialized existing Yak context in {yak_dir}")
    else:
        print(f"Initialized empty Yak context in {yak_dir}")
