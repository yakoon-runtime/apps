"""apps-runtime WebSocket handler boundary: an expected resume miss
(SessionNotFound from the handshake) ends the connection normally —
websockets must not log a handler failure. Any other error propagates.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from y5n.runtime.api.clients import SessionNotFound

import y5n.apps.runtime.__main__ as runtime_main


class FakeWebsocket:
    """Only what WebSocketServerTransport.connect() touches on the
    failure path: request headers and outbound frames."""

    def __init__(self):
        self.request = SimpleNamespace(headers={})
        self.sent: list[str] = []

    async def send(self, msg: str) -> None:
        self.sent.append(msg)


class FakeHost:
    def __init__(self, fail: Exception | None = None):
        self.fail = fail

    async def connect(self, connection, session_key=None):
        if self.fail is not None:
            raise self.fail
        raise AssertionError("success path not exercised by these tests")


@pytest.mark.asyncio
async def test_handler_consumes_expected_resume_miss(monkeypatch):
    ws = FakeWebsocket()
    monkeypatch.setattr(
        runtime_main, "_host", FakeHost(fail=SessionNotFound("Session X not found"))
    )

    # returns normally instead of failing the websocket handler
    await runtime_main.handler(ws)

    # the machine-readable error frame went out before the handshake ended
    assert json.loads(ws.sent[-1]) == {
        "type": "error",
        "code": "session_not_found",
        "message": "Session X not found",
    }


@pytest.mark.asyncio
async def test_handler_propagates_unexpected_failure(monkeypatch):
    ws = FakeWebsocket()
    monkeypatch.setattr(
        runtime_main, "_host", FakeHost(fail=RuntimeError("runtime is on fire"))
    )

    with pytest.raises(RuntimeError, match="runtime is on fire"):
        await runtime_main.handler(ws)

    # the code-less error frame still went out before propagating
    assert "code" not in json.loads(ws.sent[-1])
