"""yak runtime start|stop|status|restart — manage the runtime service."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_runtime_root


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
            return

    match args.action:
        case "start":
            _start(mgr, path)
        case "stop":
            _stop(mgr, path)
        case "status":
            _status(mgr, path)
        case "restart":
            _stop(mgr, path)
            _start(mgr, path)


def _copy_config(env_file: str, path: Path) -> None:
    import shutil

    shutil.copy2(env_file, path / "yakoon-runtime.yml")


def _start(mgr, path: Path) -> None:
    running = mgr.runtime_status(path)
    if running is not None:
        print(f"Runtime already running (pid {running})")
        return

    pid = mgr.run_runtime(path)
    if pid is None:
        print("Runtime start failed")
        return
    print(f"Runtime started (pid {pid})")
    print(f"Logs     : {path / '.yak' / 'logs' / 'runtime.log'}")


def _stop(mgr, path: Path) -> None:
    pid = mgr.stop_runtime(path)
    if pid is None:
        print("Runtime not running")
    else:
        print(f"Runtime stopped (pid {pid})")


def _status(mgr, path: Path) -> None:
    pid = mgr.runtime_status(path)
    if pid is None:
        print("Runtime not running")
    else:
        print(f"Runtime running (pid {pid})")
