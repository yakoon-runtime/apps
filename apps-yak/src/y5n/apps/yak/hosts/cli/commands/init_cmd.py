"""yak init — create a Yak context in the current directory.

``init`` is deliberately dumb: it copies the packaged ``sources.toml``
(where the world starts) into ``.yak/context.toml`` and stamps the local
identity. Everything else reads that file. Yak knows mechanisms, not
deployments — the sources are data.
"""

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

    # The sources configuration ships with the tool — data, not code.
    packaged = Path(__file__).resolve().parents[3] / "sources.toml"
    default = packaged.read_text() if packaged.exists() else ""

    # Detect known subdirectories for build-time roots (transition).
    known_dirs = ("packs", "packages")
    roots = [d for d in known_dirs if (root / d).is_dir()]

    ctx_lines = [default.rstrip()]
    if roots:
        ctx_lines.append("")
        ctx_lines.append(f"source_dirs = [{', '.join(repr(r) for r in roots)}]")
    ctx_lines.extend(
        [
            "",
            "[context]",
            "# Human-readable name of this Yak context.",
            f'name = "{root.name}"',
            "# Context creation time in UTC.",
            f'created = "{now}"',
            "# Yak context file format version.",
            'schema = "1"',
            "",
        ]
    )
    if not ctx_lines[0]:
        ctx_lines = ctx_lines[1:]

    (yak_dir / "context.toml").write_text("\n".join(ctx_lines))

    if already:
        print(f"Reinitialized existing Yak context in {yak_dir}")
    else:
        print(f"Initialized empty Yak context in {yak_dir}")
