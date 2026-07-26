from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path


def run(args, mgr) -> None:
    path = find_installation_path()
    if path is None:
        print("Not inside a Yak installation.")
        print("Run 'yak install' first or cd into one.")
        return

    match args.action:
        case "start":
            _start(path)
        case "stop":
            _stop(path)
        case "status":
            _status(path)
        case "restart":
            _stop(path)
            _start(path)


def _start(path: Path) -> None:
    pid_file = path / ".yak" / "runtime.pid"

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"Runtime already running (pid {pid})")
            return
        except (ProcessLookupError, ValueError):
            pid_file.unlink(missing_ok=True)

    # Determine port from config
    port = 9100
    config = path / "yakoon-runtime.yml"
    if config.exists():
        try:
            import yaml

            cfg = yaml.safe_load(config.read_text()) or {}
            port = cfg.get("listen", {}).get("port", 9100)
        except Exception:
            pass

    log_dir = path / ".yak" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "runtime.log"

    wrapper = path / ".venv" / "bin" / "yakoon-runtime"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import ctypes, ctypes.util\n"
        "libc = ctypes.CDLL(ctypes.util.find_library('c'))\n"
        "libc.prctl(15, b'yakoon-runtime', 0, 0, 0)\n"
        "from y5n.apps.runtime.__main__ import main\n"
        "main()\n"
    )
    wrapper.chmod(0o755)

    with open(log_file, "a") as lf:
        proc = subprocess.Popen(
            [str(wrapper)], cwd=path, stdout=lf, stderr=lf
        )
    pid_file.write_text(str(proc.pid))
    print(f"Runtime started (pid {proc.pid})")
    print(f"Logs     : {log_file}")


def _stop(path: Path) -> None:
    pid_file = path / ".yak" / "runtime.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"Runtime stopped (pid {pid})")
        except ProcessLookupError:
            print("Runtime not running")
        except ValueError:
            print("Invalid PID file")
        pid_file.unlink(missing_ok=True)
    else:
        print("Runtime not running")


def _status(path: Path) -> None:
    pid_file = path / ".yak" / "runtime.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"Runtime running (pid {pid})")
        except (ProcessLookupError, ValueError):
            print("Runtime not running")
    else:
        print("Runtime not running")
