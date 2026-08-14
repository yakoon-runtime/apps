"""Runtime process management — start, stop, status of the Yakoon runtime.

Process supervision is operational concern, not installation: this
module knows how to run a background service, guard its port and
record its pid. It knows nothing about catalogs, components or
resolution. The installation status transition (RUNNING/STOPPED) is
handled through an injected callback.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

RUNTIME_CONFIG_FILENAME = "yakoon-runtime.yml"
RUNTIME_DEFAULT_HOST = "127.0.0.1"
RUNTIME_DEFAULT_PORT = 9100
RUNTIME_START_TIMEOUT = 20.0


@dataclass(frozen=True)
class RuntimeOccupant:
    """A process listening on a runtime's port."""

    pid: int
    yakoon: bool


class RuntimeService:
    """Supervise one runtime per installation root."""

    def __init__(
        self,
        *,
        mark_running: Callable[[Path, bool], None] | None = None,
        timeout: float = RUNTIME_START_TIMEOUT,
    ) -> None:
        self._mark_running = mark_running
        self._timeout = timeout

    def run(self, path: Path) -> int | None:
        """Start the runtime service for a root; return the new pid.

        The process runs in the background via a venv wrapper script; the
        pid is recorded at ``.yak/runtime.pid``. Returns None when the
        runtime is already running. Raises RuntimeError when the runtime
        port is taken or the process does not become ready within
        ``timeout`` seconds — in both cases the start is aborted and no
        pid is recorded.
        """
        pid_file = path / ".yak" / "runtime.pid"
        if self._read_pid(pid_file) is not None:
            return None

        host, port = self.listen_address(path)

        occupants = self._holding_pids(port)
        if occupants or self._port_occupied(host, port):
            raise RuntimeError(self._collision_message(host, port, occupants))

        log_dir = path / ".yak" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "runtime.log"
        log_offset = log_file.stat().st_size if log_file.exists() else 0

        venv_python = path / ".venv" / "bin" / "python"
        wrapper = path / ".venv" / "bin" / "yakoon-runtime"
        wrapper.write_text(
            f"#!{venv_python}\n"
            "import ctypes, ctypes.util\n"
            "libc = ctypes.CDLL(ctypes.util.find_library('c'))\n"
            "libc.prctl(15, b'yakoon-runtime', 0, 0, 0)\n"
            "from y5n.apps.runtime.__main__ import main\n"
            "main()\n"
        )
        wrapper.chmod(0o755)

        with open(log_file, "a") as lf:
            proc = subprocess.Popen([str(wrapper)], cwd=path, stdout=lf, stderr=lf)

        ready, tail = self._wait_ready(
            host, port, proc, log_file=log_file, offset=log_offset
        )
        if not ready:
            proc.terminate()
            pid_file.unlink(missing_ok=True)
            self._set_running(path, running=False)
            raise RuntimeError(
                f"Runtime failed to start within {self._timeout:g}s (pid {proc.pid}).\n"
                f"{tail.strip() or 'No output yet.'}"
            )

        pid_file.write_text(str(proc.pid))
        self._set_running(path, running=True)
        return proc.pid

    def stop(self, path: Path) -> int | None:
        """Stop the runtime service for a root; return the stopped pid."""
        pid_file = path / ".yak" / "runtime.pid"
        pid = self._read_pid(pid_file)
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        pid_file.unlink(missing_ok=True)
        self._set_running(path, running=False)
        return pid

    def status(self, path: Path) -> int | None:
        """Return the running runtime pid for a root, or None."""
        return self._read_pid(path / ".yak" / "runtime.pid")

    def occupant(self, path: Path) -> RuntimeOccupant | None:
        """The first process listening on the runtime's port, or None.

        Best-effort: an untracked listener (e.g. a stale runtime left
        over from another installation) is reported so the operator can
        release the port. Returns None when the port is free or the
        listener cannot be determined.
        """
        _, port = self.listen_address(path)
        for pid in self._holding_pids(port):
            return RuntimeOccupant(pid=pid, yakoon=self._is_yakoon_runtime(pid))
        return None

    # ── Port / readiness helpers ──

    def listen_address(self, path: Path) -> tuple[str, int]:
        """The address the runtime will listen on for a root.

        Mirrors the runtime app's config search: the first
        ``yakoon-runtime.yml`` found walking up from the root, then the
        user config, defaulting to the runtime default address.
        """
        for parent in [path, *path.parents]:
            cfg = parent / RUNTIME_CONFIG_FILENAME
            if cfg.is_file():
                return self._parse_listen_config(cfg)
        user_cfg = Path.home() / ".config" / "y5n" / RUNTIME_CONFIG_FILENAME
        if user_cfg.is_file():
            return self._parse_listen_config(user_cfg)
        return (RUNTIME_DEFAULT_HOST, RUNTIME_DEFAULT_PORT)

    @staticmethod
    def _parse_listen_config(cfg: Path) -> tuple[str, int]:
        try:
            data = yaml.safe_load(cfg.read_text()) or {}
        except OSError:
            return (RUNTIME_DEFAULT_HOST, RUNTIME_DEFAULT_PORT)
        listen = data.get("listen") or {}
        host = listen.get("host", RUNTIME_DEFAULT_HOST)
        try:
            port = int(listen.get("port", RUNTIME_DEFAULT_PORT))
        except (TypeError, ValueError):
            port = RUNTIME_DEFAULT_PORT
        return (str(host), port)

    @staticmethod
    def _port_occupied(host: str, port: int) -> bool:
        """Whether a socket is already listening on the address."""
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return False
        except OSError:
            return True
        finally:
            sock.close()

    def _holding_pids(self, port: int) -> list[int]:
        """Pids listening on ``port`` (Linux /proc, best-effort)."""
        inodes: set[str] = set()
        for table in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                with open(table) as f:
                    next(f)
                    for line in f:
                        parts = line.split()
                        if len(parts) < 10 or parts[3] != "0A":
                            continue
                        hexport = parts[1].rpartition(":")[2]
                        try:
                            if int(hexport, 16) != port:
                                continue
                        except ValueError:
                            continue
                        inodes.add(parts[9])
            except OSError:
                continue

        pids: list[int] = []
        for pid in self._iter_pids():
            try:
                fd_dir = Path(f"/proc/{pid}/fd")
                for fd in fd_dir.iterdir():
                    try:
                        target = os.readlink(fd)
                    except OSError:
                        continue
                    if target.startswith("socket:["):
                        if target[len("socket:[") : -1] in inodes:
                            pids.append(pid)
                            break
            except OSError:
                continue
        return pids

    @staticmethod
    def _iter_pids() -> list[int]:
        try:
            return [int(e.name) for e in Path("/proc").iterdir() if e.name.isdigit()]
        except OSError:
            return []

    @staticmethod
    def _is_yakoon_runtime(pid: int) -> bool:
        try:
            cmdline = (Path(f"/proc/{pid}/cmdline").read_bytes() or b"").decode(
                errors="replace"
            )
        except OSError:
            return False
        return "yakoon-runtime" in cmdline

    def _collision_message(self, host: str, port: int, occupants: list[int]) -> str:
        if occupants:
            holder = ", ".join(
                f"pid {p}" + (" (yakoon-runtime)" if self._is_yakoon_runtime(p) else "")
                for p in occupants
            )
            return (
                f"Port {host}:{port} is already in use by {holder}.\n"
                "If it is a stale runtime, stop it first — e.g. 'yak runtime stop' "
                "from its installation or 'kill <pid>'."
            )
        return (
            f"Port {host}:{port} is already in use by another process.\n"
            "Free the port and try again."
        )

    def _wait_ready(
        self,
        host: str,
        port: int,
        proc,
        *,
        log_file: Path,
        offset: int,
    ) -> tuple[bool, str]:
        """Poll until the runtime accepts connections or the process dies.

        Returns (ready, log_tail). Readiness means the socket accepts a
        TCP connection — the WebSocket server is actually listening, not
        merely spawned. ``offset`` limits the log tail to what the new
        process has written.
        """
        deadline = time.monotonic() + self._timeout
        while True:
            if self._can_connect(host, port):
                return True, self._read_log_tail(log_file, offset)
            if proc.poll() is not None:
                return False, self._read_log_tail(log_file, offset)
            if time.monotonic() >= deadline:
                return False, self._read_log_tail(log_file, offset)
            time.sleep(0.1)

    @staticmethod
    def _can_connect(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            return False

    @staticmethod
    def _read_log_tail(log_file: Path, offset: int) -> str:
        try:
            with open(log_file, errors="replace") as f:
                f.seek(offset)
                return "\n".join(f.read().splitlines()[-10:])
        except OSError:
            return ""

    @staticmethod
    def _read_pid(pid_file: Path) -> int | None:
        if not pid_file.exists():
            return None
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (OSError, ValueError):
            return None

    def _set_running(self, path: Path, *, running: bool) -> None:
        if self._mark_running is not None:
            self._mark_running(path, running)
