"""yak runtime start|stop|status|restart — manage the runtime service."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_runtime_root
from y5n.apps.yak.runtime.service import RuntimeService


def run(args, mgr) -> None:
    env_file = getattr(args, "environment", None)
    if env_file:
        path = Path(env_file).resolve().parent
        _copy_config(env_file, path)
    else:
        path = find_runtime_root()
        if path is None:
            print("Not inside a Yak context or installation.")
            print("Run 'yak install <name>' or 'yak init' first.")
            raise SystemExit(1)

    svc = RuntimeService()
    match args.action:
        case "start":
            _start(svc, path)
        case "stop":
            _stop(svc, path)
        case "status":
            _status(svc, path)
        case "restart":
            _stop(svc, path)
            _start(svc, path)


def _copy_config(env_file: str, path: Path) -> None:
    import shutil

    shutil.copy2(env_file, path / "yakoon-runtime.yml")


def _start(svc: RuntimeService, path: Path) -> None:
    running = svc.status(path)
    if running is not None:
        print(f"Runtime already running (pid {running})")
        return

    try:
        pid = svc.run(path)
    except RuntimeError as exc:
        print("Runtime start failed.")
        print(str(exc))
        raise SystemExit(1)
    if pid is None:
        print("Runtime start failed")
        raise SystemExit(1)
    print(f"Runtime started (pid {pid})")
    print(f"Logs     : {path / '.yak' / 'logs' / 'runtime.log'}")


def _stop(svc: RuntimeService, path: Path) -> None:
    pid = svc.stop(path)
    if pid is None:
        print("Runtime not running")
    else:
        print(f"Runtime stopped (pid {pid})")
    _report_untracked(svc, path, tracked=pid)


def _status(svc: RuntimeService, path: Path) -> None:
    pid = svc.status(path)
    if pid is None:
        print("Runtime not running")
    else:
        print(f"Runtime running (pid {pid})")
    _report_untracked(svc, path, tracked=pid)


def _report_untracked(svc: RuntimeService, path: Path, *, tracked: int | None) -> None:
    """Warn about a listener that is not the tracked runtime."""
    occupant = svc.occupant(path)
    if occupant is None or occupant.pid == tracked:
        return
    kind = " (yakoon-runtime)" if occupant.yakoon else ""
    print(
        f"Note: pid {occupant.pid}{kind} is still listening on the runtime "
        "port but is not tracked by this installation. "
        "Stop it before starting this runtime."
    )
