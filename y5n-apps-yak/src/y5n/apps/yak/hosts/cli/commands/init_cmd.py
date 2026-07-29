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

    # Detect known subdirectories for roots
    known_dirs = ("packs", "runtime", "apps", "sdk")
    roots = [d for d in known_dirs if (root / d).is_dir()]

    ctx_lines = [
        f"[context]",
        f'name = "{root.name}"',
        f'created = "{now}"',
        f'schema = "1"',
    ]
    if roots:
        ctx_lines.append("")
        ctx_lines.append("[sources]")
        ctx_lines.append(f'dirs = [{", ".join(repr(r) for r in roots)}]')
    ctx_lines.extend(["", "[logs]", 'path = ".yak/logs"', ""])

    (yak_dir / "context.toml").write_text("\n".join(ctx_lines))

    if already:
        print(f"Reinitialized existing Yak context in {yak_dir}")
    else:
        print(f"Initialized empty Yak context in {yak_dir}")
