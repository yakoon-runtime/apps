"""Elements-mode Form in the real Shell path.

The io.form(elements=...) projection flows through the real engine wire
(normalize → EventDispatcher → EventTraversal) into the real renderer.
Proves that SDK YDS presentation models (Heading/Rule/Text, inline-list
text) and grouped fields render as the SIGN IN composition.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Rule as TextualRule
from y5n.apps.shell.output import CopyableStatic, TextualOutput
from y5n.runtime.api.document.normalize import normalize
from y5n.runtime.api.runtime import Event
from y5n.runtime.api.runtime.input import InputContext
from y5n.runtime.engine.document.transport.dispatcher import EventDispatcher
from y5n.runtime.engine.document.transport.factory import EventFactory
from y5n.runtime.engine.document.transport.traversal import EventTraversal
from y5n.sdk import io
from y5n.sdk.models import Field, Heading, InlineText, Rule, Text


class _StubSession:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


def _sign_in_projection() -> dict:
    gen = io.form(
        elements=[
            Heading(text=[InlineText(text="SIGN IN")]),
            Rule(),
            Text(text=[InlineText(text="Authenticate to continue.")]),
            Field(key="user", title="Username"),
            Field(key="password", title="Password", secret=True),
        ]
    ).__await__()
    pulse = gen.send(None)
    return pulse.effects[1].view


async def _wire_events(projection: dict) -> list:
    doc = normalize(projection)
    session = _StubSession()
    dispatcher = EventDispatcher(EventFactory(), EventTraversal())
    await dispatcher.begin_projection(
        session, doc, ctx=InputContext(), job_id="test:form"
    )
    await dispatcher.emit_projection(session, doc)
    await dispatcher.finish_projection(session, doc)
    return session.events


class _Harness(App):
    def __init__(self, events):
        super().__init__()
        self.events = events
        self.container = VerticalScroll(classes="tab-output")
        self.output = TextualOutput(self.container)

    def compose(self) -> ComposeResult:
        yield self.container

    async def feed(self):
        for event in self.events:
            await self.output.view(event)


def _rendered_text(app) -> str:
    parts = []
    for static in app.query(CopyableStatic):
        content = static.content
        parts.append(content.plain if hasattr(content, "plain") else str(content))
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_elements_projection_renders_sign_in_composition():
    app = _Harness(await _wire_events(_sign_in_projection()))
    async with app.run_test() as pilot:
        await app.feed()
        await pilot.pause()

        # heading renders its inline text
        headings = [w for w in app.query(CopyableStatic) if w.has_class("heading")]
        assert len(headings) == 1
        assert headings[0].content.plain == "SIGN IN"

        # the rule is a native Rule widget
        assert len(app.query(TextualRule)) == 1

        # text block renders its inline text
        assert "Authenticate to continue." in _rendered_text(app)

        # both fields render in one grouped fields node
        fields_groups = app.query("Vertical.fields")
        assert len(fields_groups) == 1
        group_text = _rendered_text(app)
        assert "Username" in group_text
        assert "Password" in group_text

        # the first field is active and not secret
        assert app.output.active_field_value == ""
        assert app.output.active_field_secret is False


@pytest.mark.asyncio
async def test_elements_projection_tracks_active_secret_field():
    gen = io.form(
        elements=[
            Heading(text=[InlineText(text="SIGN IN")]),
            Rule(),
            Field(key="user", title="Username"),
            Field(key="password", title="Password", secret=True),
        ]
    ).__await__()
    gen.send(None)  # initial prompt (user active)
    gen.send(None)  # receive pulse
    gen.send(Event(payload="stefan"))  # re-render: no active field yet
    pulse = gen.send(None)  # password prompt (password active)
    view = pulse.effects[1].view

    app = _Harness(await _wire_events(view))
    async with app.run_test() as pilot:
        await app.feed()
        await pilot.pause()

        # the password prompt marks the secret field active — secret
        # detection follows the projection
        assert app.output.active_field_secret is True
        group_text = _rendered_text(app)
        assert "Username" in group_text
        assert "stefan" in group_text
