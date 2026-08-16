import socket
import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.runtime.service import RuntimeService


def _svc() -> RuntimeService:
    return RuntimeService()


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
    svc = _svc()
    with tempfile.TemporaryDirectory() as tmp:
        assert svc.listen_address(Path(tmp)) == ("127.0.0.1", 9100)


def test_runtime_listen_reads_config():
    svc = _svc()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_runtime_config(root, 9123, host="0.0.0.0")
        assert svc.listen_address(root) == ("0.0.0.0", 9123)


def test_port_occupied_detects_listener():
    svc = _svc()
    port = _free_port()
    assert svc._port_occupied("127.0.0.1", port) is False
    sock = _listen_socket(port)
    try:
        assert svc._port_occupied("127.0.0.1", port) is True
    finally:
        sock.close()


def test_run_runtime_raises_on_port_collision():
    svc = _svc()
    port = _free_port()
    sock = _listen_socket(port)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_runtime_config(root, port)
            with pytest.raises(RuntimeError, match="already in use"):
                svc.run(root)
    finally:
        sock.close()


def test_wait_ready_when_listening():
    svc = _svc()
    port = _free_port()
    sock = _listen_socket(port)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "runtime.log"

            class AliveProc:
                def poll(self) -> None:
                    return None

            ready, _ = svc._wait_ready(
                "127.0.0.1",
                port,
                AliveProc(),
                log_file=log_file,
                offset=0,
            )
            assert ready is True
    finally:
        sock.close()


def test_wait_ready_detects_dead_process():
    svc = _svc()
    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / "runtime.log"
        log_file.write_text("traceback\nboom\n")

        class DeadProc:
            def poll(self) -> int:
                return 1

        ready, tail = svc._wait_ready(
            "127.0.0.1",
            1,
            DeadProc(),
            log_file=log_file,
            offset=0,
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
    svc = _svc()
    monkeypatch.setattr(
        "y5n.apps.yak.runtime.service.subprocess.Popen",
        lambda *a, **k: _FakeProc(),
    )
    monkeypatch.setattr(svc, "_can_connect", lambda host, port: True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".yak" / "logs").mkdir(parents=True)
        _write_runtime_config(root, _free_port())

        pid = svc.run(root)
        assert pid == 4242
        assert (root / ".yak" / "runtime.pid").read_text().strip() == "4242"


def test_run_runtime_cleans_up_on_failure(monkeypatch):
    svc = _svc()
    monkeypatch.setattr(
        "y5n.apps.yak.runtime.service.subprocess.Popen",
        lambda *a, **k: _FakeProc(dead=True),
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".yak" / "logs").mkdir(parents=True)
        _write_runtime_config(root, _free_port())

        with pytest.raises(RuntimeError, match="failed to start"):
            svc.run(root)
        assert not (root / ".yak" / "runtime.pid").exists()


def test_is_yakoon_runtime_for_current_process():
    import os

    svc = _svc()
    assert svc._is_yakoon_runtime(os.getpid()) is False
