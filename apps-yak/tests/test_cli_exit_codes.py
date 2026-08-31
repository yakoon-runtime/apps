"""CLI exit-code contract (host layer).

The command contract: a command returns normally on success and raises
SystemExit for a reported failure; ``main()`` turns any other exception
into an exit code and the process code reflects the command outcome.

    success            → exit 0
    reported failure   → SystemExit(1)
    unexpected error   → SystemExit(1), message on stderr
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest


class _StubManager:
    """A minimal stand-in for InstallationManager."""

    calls: list[str] = []


def _args(**kw) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


def test_main_returns_zero_on_success(monkeypatch, capsys):
    from y5n.apps.yak.hosts.cli import main as cli_main

    def _func(args, mgr) -> None:
        assert isinstance(mgr, _StubManager)

    parser = types.SimpleNamespace(parse_args=lambda: _args(func=_func))
    monkeypatch.setattr(cli_main, "build_parser", lambda: parser)
    monkeypatch.setattr(cli_main, "_build_manager", _StubManager)
    monkeypatch.setattr(sys, "argv", ["yak", "run"])

    assert cli_main.main() == 0


def test_main_reraises_systemexit(monkeypatch):
    from y5n.apps.yak.hosts.cli import main as cli_main

    def _func(args, mgr) -> None:
        raise SystemExit(1)

    parser = types.SimpleNamespace(parse_args=lambda: _args(func=_func))
    monkeypatch.setattr(cli_main, "build_parser", lambda: parser)
    monkeypatch.setattr(cli_main, "_build_manager", _StubManager)
    monkeypatch.setattr(sys, "argv", ["yak", "run"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()
    assert exc.value.code == 1


def test_main_wraps_unexpected_exception(monkeypatch, capsys):
    from y5n.apps.yak.hosts.cli import main as cli_main

    def _func(args, mgr) -> None:
        raise ValueError("boom")

    parser = types.SimpleNamespace(parse_args=lambda: _args(func=_func))
    monkeypatch.setattr(cli_main, "build_parser", lambda: parser)
    monkeypatch.setattr(cli_main, "_build_manager", _StubManager)
    monkeypatch.setattr(sys, "argv", ["yak", "run"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()
    assert exc.value.code == 1
    assert "boom" in capsys.readouterr().err


def test_runtime_start_failure_exits_nonzero(monkeypatch, tmp_path):
    """The reported failure we hit in the field: missing secret → non-zero."""
    from y5n.apps.yak.hosts.cli.commands import runtime as runtime_cmd

    class _FailingService:
        def status(self, path):
            return None

        def run(self, path):
            raise RuntimeError(
                "EventStoreFactory: dsn environment variable not set: IDENT_DATABASE"
            )

    monkeypatch.setattr(runtime_cmd, "find_runtime_root", lambda: Path(tmp_path))
    monkeypatch.setattr(runtime_cmd, "RuntimeService", _FailingService)

    with pytest.raises(SystemExit) as exc:
        runtime_cmd.run(_args(action="start"), None)
    assert exc.value.code == 1


def test_runtime_start_success_returns(monkeypatch, tmp_path, capsys):
    from y5n.apps.yak.hosts.cli.commands import runtime as runtime_cmd

    class _OkService:
        def status(self, path):
            return None

        def run(self, path):
            return 1234

    monkeypatch.setattr(runtime_cmd, "find_runtime_root", lambda: Path(tmp_path))
    monkeypatch.setattr(runtime_cmd, "RuntimeService", _OkService)

    runtime_cmd.run(_args(action="start"), None)
    assert "Runtime started (pid 1234)" in capsys.readouterr().out
