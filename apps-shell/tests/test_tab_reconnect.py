"""Shell reconnect contract: the retained session key drives RESUME, and
only a machine-readable SessionNotFound falls back to a fresh CREATE.

Any other failure propagates and must leave the retained key untouched —
the next reconnect retries the same session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from y5n.runtime.api.clients import ClientConnection, SessionNotFound
from y5n.apps.shell.tab import RuntimeTab


def _make_tab() -> RuntimeTab:
    return RuntimeTab(
        name="test",
        pane_id="test-0",
        on_connect=AsyncMock(),
        on_disconnect=AsyncMock(),
    )


class FakeTransport:
    """Records connect() calls; scripts the outcomes in order."""

    def __init__(self, url: str, outcomes: list):
        self._url = url
        self.outcomes = list(outcomes)
        self.calls: list[str | None] = []

    async def connect(self, on_emit, session_key: str | None = None):
        self.calls.append(session_key)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _connection(key: str) -> ClientConnection:
    connection = ClientConnection(emit=AsyncMock(), dispatch=AsyncMock())
    connection.session_key = key
    return connection


X = "system/session/runtime#boot-x-0"
Y = "system/session/runtime#boot-y-0"


@pytest.mark.asyncio
async def test_reconnect_falls_back_to_create_on_session_not_found():
    """RESUME X fails with SessionNotFound → exactly one fresh CREATE →
    the tab retains the new key Y."""
    tab = _make_tab()
    tab._session_key = X
    transport = FakeTransport(
        "ws://localhost:9100",
        outcomes=[
            SessionNotFound(f"Session {X} not found"),
            _connection(Y),
        ],
    )

    await tab.connect(transport)

    assert transport.calls == [X, None]  # RESUME X first, then keyless CREATE
    assert tab._session_key == Y
    assert tab.connection.session_key == Y


@pytest.mark.asyncio
async def test_reconnect_generic_failure_keeps_retained_key():
    """Any other failure propagates and must not overwrite the retained
    key — the next reconnect retries the same session."""
    tab = _make_tab()
    tab._session_key = X
    transport = FakeTransport(
        "ws://localhost:9100",
        outcomes=[RuntimeError("runtime is on fire")],
    )

    with pytest.raises(RuntimeError, match="runtime is on fire"):
        await tab.connect(transport)

    assert transport.calls == [X]  # no fallback CREATE
    assert tab._session_key == X

    # the next reconnect retries X and succeeds
    transport2 = FakeTransport(
        "ws://localhost:9100",
        outcomes=[_connection(X)],
    )
    await tab.connect(transport2)
    assert transport2.calls == [X]
    assert tab._session_key == X


@pytest.mark.asyncio
async def test_fresh_tab_connects_without_key():
    """A fresh tab has no retained key: plain CREATE, key learned from the
    connection afterwards."""
    tab = _make_tab()
    transport = FakeTransport(
        "ws://localhost:9100",
        outcomes=[_connection(X)],
    )

    await tab.connect(transport)

    assert transport.calls == [None]
    assert tab._session_key == X
