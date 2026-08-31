"""yak logs — show logs for the current context."""

from __future__ import annotations

from y5n.apps.yak.hosts.cli.cwd import find_context_root


def run(args, mgr) -> None:
    ctx = find_context_root()
    if ctx is None:
        print("Not inside a Yak context.")
        print("Run 'yak init' first or cd into one.")
        raise SystemExit(1)

    log_dir = ctx / ".yak" / "logs"
    if not log_dir.exists() or not any(log_dir.iterdir()):
        print("No logs found.")
        return

    target = args.target if hasattr(args, "target") and args.target else None
    if target:
        log_file = log_dir / f"{target}.log"
        if log_file.exists():
            print(log_file.read_text())
        else:
            print(f"No log found for '{target}'.")
        return

    print(f"Logs in {log_dir}:")
    for f in sorted(log_dir.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name} ({size} bytes)")
