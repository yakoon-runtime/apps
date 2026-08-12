import socket
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _mgr() -> InstallationManager:
    return InstallationManager(FileRepository(), DirectoryArtifactStore())


def _free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _listen_socket(port: int):
    sock = socket.socket()
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


def _write_runtime_config(root: Path, port: int, host: str = "127.0.0.1") -> None:
    (root / "yakoon-runtime.yml").write_text(
        f"listen:\n  host: {host}\n  port: {port}\n"
    )


def test_runtime_listen_defaults():
    mgr = _mgr()
    with tempfile.TemporaryDirectory() as tmp:
        assert mgr._runtime_listen(Path(tmp)) == ("127.0.0.1", 9100)


def test_runtime_listen_reads_config():
    mgr = _mgr()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_runtime_config(root, 9123, host="0.0.0.0")
        assert mgr._runtime_listen(root) == ("0.0.0.0", 9123)


def test_port_occupied_detects_listener():
    mgr = _mgr()
    port = _free_port()
    assert mgr._port_occupied("127.0.0.1", port) is False
    sock = _listen_socket(port)
    try:
        assert mgr._port_occupied("127.0.0.1", port) is True
    finally:
        sock.close()


def test_run_runtime_raises_on_port_collision():
    mgr = _mgr()
    port = _free_port()
    sock = _listen_socket(port)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_runtime_config(root, port)
            with pytest.raises(RuntimeError, match="already in use"):
                mgr.run_runtime(root)
    finally:
        sock.close()


def test_wait_ready_when_listening():
    mgr = _mgr()
    port = _free_port()
    sock = _listen_socket(port)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "runtime.log"

            class AliveProc:
                def poll(self) -> None:
                    return None

            ready, _ = mgr._wait_ready(
                "127.0.0.1",
                port,
                AliveProc(),
                log_file=log_file,
                offset=0,
                timeout=5.0,
            )
            assert ready is True
    finally:
        sock.close()


def test_wait_ready_detects_dead_process():
    mgr = _mgr()
    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / "runtime.log"
        log_file.write_text("traceback\nboom\n")

        class DeadProc:
            def poll(self) -> int:
                return 1

        ready, tail = mgr._wait_ready(
            "127.0.0.1",
            1,
            DeadProc(),
            log_file=log_file,
            offset=0,
            timeout=1.0,
        )
        assert ready is False
        assert "boom" in tail


class _FakeProc:
    def __init__(self, *, dead: bool = False) -> None:
        self.pid = 4242
        self._dead = dead

    def poll(self) -> int | None:
        return 1 if self._dead else None

    def terminate(self) -> None:
        return None


def test_run_runtime_writes_pid_after_ready(monkeypatch):
    mgr = _mgr()
    monkeypatch.setattr(
        "y5n.apps.yak.installation.manager.subprocess.Popen",
        lambda *a, **k: _FakeProc(),
    )
    monkeypatch.setattr(mgr, "_can_connect", lambda host, port: True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".yak" / "logs").mkdir(parents=True)
        _write_runtime_config(root, _free_port())

        pid = mgr.run_runtime(root)
        assert pid == 4242
        assert (root / ".yak" / "runtime.pid").read_text().strip() == "4242"


def test_run_runtime_cleans_up_on_failure(monkeypatch):
    mgr = _mgr()
    monkeypatch.setattr(
        "y5n.apps.yak.installation.manager.subprocess.Popen",
        lambda *a, **k: _FakeProc(dead=True),
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".yak" / "logs").mkdir(parents=True)
        _write_runtime_config(root, _free_port())

        with pytest.raises(RuntimeError, match="failed to start"):
            mgr.run_runtime(root)
        assert not (root / ".yak" / "runtime.pid").exists()


def test_is_yakoon_runtime_for_current_process():
    import os

    mgr = _mgr()
    assert mgr._is_yakoon_runtime(os.getpid()) is False
