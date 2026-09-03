"""Field.secret in the Shell renderer: detection, masking, mode reset.

The Shell honors the projection's field ``secret`` property by not
visibly echoing entered characters — the raw value still reaches the
submitted event unchanged. Ordinary fields behave exactly as before;
secret state never leaks into a later ordinary field.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
from y5n.apps.shell.input import MASK, ShellInput
from y5n.apps.shell.output import CopyableStatic, TextualOutput
from y5n.runtime.api.document.normalize import normalize
from y5n.runtime.api.runtime.input import InputContext
from y5n.runtime.engine.document.transport.dispatcher import EventDispatcher
from y5n.runtime.engine.document.transport.factory import EventFactory
from y5n.runtime.engine.document.transport.traversal import EventTraversal
from y5n.sdk.models import Document as SdkDocument
from y5n.sdk.models import Field as SdkField
from y5n.sdk.models import Fields as SdkFields
from y5n.sdk.models import Header as SdkHeader


def _output() -> TextualOutput:
    return TextualOutput(container=Static())


def test_active_secret_field_is_detected():
    out = _output()
    out._make_fields(
        {
            "props": {
                "fields": [
                    {"name": "user", "title": "User", "state": "done", "value": "stefan"},
                    {
                        "name": "password",
                        "title": "Password",
                        "state": "active",
                        "value": "",
                        "secret": True,
                    },
                ]
            }
        }
    )
    assert out.active_field_value == ""
    assert out.active_field_secret is True


def test_active_ordinary_field_is_not_secret():
    out = _output()
    out._make_fields(
        {
            "props": {
                "fields": [
                    {"name": "user", "title": "User", "state": "active", "value": ""}
                ]
            }
        }
    )
    assert out.active_field_value == ""
    assert out.active_field_secret is False


@pytest.mark.asyncio
async def test_secret_values_are_never_displayed():
    out = _output()
    widget = out._make_fields(
        {
            "props": {
                "fields": [
                    {
                        "name": "password",
                        "title": "Password",
                        "state": "active",
                        "value": "hunter2",
                        "secret": True,
                    },
                    {"name": "user", "title": "User", "state": "done", "value": "stefan"},
                    {
                        "name": "token",
                        "title": "Token",
                        "state": "done",
                        "value": "s3cr3t-t0ken",
                        "secret": True,
                    },
                ]
            }
        }
    )

    class _Viewer(App):
        def compose(self) -> ComposeResult:
            yield widget

    app = _Viewer()
    async with app.run_test() as pilot:
        await pilot.pause()
        parts = []
        for static in app.query(CopyableStatic):
            content = static.content
            parts.append(content.plain if hasattr(content, "plain") else str(content))
        text = "\n".join(parts)

    assert "hunter2" not in text
    assert "s3cr3t-t0ken" not in text
    assert "stefan" in text  # ordinary value stays visible
    assert MASK in text


class _Harness(App):
    def __init__(self):
        super().__init__()
        self.submitted = []
        self.shell_input = ShellInput(on_submit=self._submit)

    def compose(self) -> ComposeResult:
        yield self.shell_input

    async def _submit(self, text: str, direct: bool, echo: str | None = None) -> None:
        self.submitted.append((text, direct, echo))


@pytest.mark.asyncio
async def test_secret_typing_is_masked_but_raw_is_preserved():
    app = _Harness()
    async with app.run_test() as pilot:
        inp = app.shell_input
        inp.focus()
        await pilot.pause()

        inp.set_secret(True)
        assert inp.secret is True

        await pilot.press(*"hunter2")
        assert inp._raw == "hunter2"
        assert "hunter2" not in inp.text
        assert MASK in inp.text

        await pilot.press("backspace")
        assert inp._raw == "hunter"
        await pilot.press("2")
        assert inp._raw == "hunter2"

        await pilot.press("enter")
        assert app.submitted == [("hunter2", False, MASK * 7)]  # raw reaches submit
        assert inp.text == ""


@pytest.mark.asyncio
async def test_ordinary_input_is_unaffected_without_secret():
    app = _Harness()
    async with app.run_test() as pilot:
        inp = app.shell_input
        inp.focus()
        await pilot.pause()

        await pilot.press(*"hello")
        assert inp.text == "hello"
        assert inp.secret is False

        await pilot.press("enter")
        assert app.submitted == [("hello", False, "hello")]


@pytest.mark.asyncio
async def test_mode_reset_without_leak():
    app = _Harness()
    async with app.run_test() as pilot:
        inp = app.shell_input
        inp.focus()
        await pilot.pause()

        inp.set_secret(True)
        await pilot.press(*"hunter2")
        assert inp._raw == "hunter2"

        inp.set_secret(False)
        assert inp.secret is False
        await pilot.press(*"abc")
        assert "abc" in inp.text  # ordinary typing is visible again
        assert inp._raw == ""

        # a fresh secret mode starts empty — nothing leaks across
        inp.set_secret(True)
        await pilot.press(*"xy")
        assert inp._raw == "xy"
        inp.set_secret(False)
        assert inp.text == ""


# ---------------------------------------------------------------------------
# REAL PATH REGRESSION
#
# The unit tests above feed hand-built projections directly into
# _make_fields / ShellInput. The real runtime wire differs in two decisive
# ways, which previously let the raw password leak in the running Shell:
#
#   1. A projection arrives as THREE events (begin/reset, append, finish)
#      and the finish event carries no fields node.
#   2. io.prompt wire fields carry ``secret`` but NO ``state``/``value``.
#
# These tests drive the real engine (normalize -> EventDispatcher) into the
# real renderer + mounted input, exactly like RuntimeTab does.
# ---------------------------------------------------------------------------


class _StubSession:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


async def _real_su_password_events(secret: bool = True):
    """su.py's password projection through the real engine wire."""
    projection = SdkDocument(
        header=SdkHeader(title="Password"),
        blocks=[
            SdkFields(
                fields=[SdkField(key="password", title="Password", secret=secret)]
            )
        ],
    ).to_dict()
    doc = normalize(projection)
    session = _StubSession()
    dispatcher = EventDispatcher(EventFactory(), EventTraversal())
    await dispatcher.begin_projection(session, doc, ctx=InputContext(), job_id="test:su")
    await dispatcher.emit_projection(session, doc)
    await dispatcher.finish_projection(session, doc)
    return session.events


@pytest.mark.asyncio
async def test_finish_event_does_not_clobber_active_secret():
    """The empty finish event must not reset the active secret field.

    Regression: view() reset the active-field state on EVERY event, so the
    trailing finish event wiped the state the patch event had established,
    and _sync_input_with_form switched the input back to ordinary mode —
    raw password characters became visible while typing.
    """
    app = _RealShellHarness(await _real_su_password_events())
    async with app.run_test() as pilot:
        await pilot.pause()
        for event in app.events:
            await app.output.view(event)
        await pilot.pause()

        assert app.output.active_field_secret is True
        assert app.output.active_field_value == ""


class _RealShellHarness(App):
    """Container + input, synced like RuntimeTab._make_view_callback."""

    def __init__(self, events):
        super().__init__()
        self.events = events
        self.submitted = []
        self.container = VerticalScroll(classes="tab-output")
        self.output = TextualOutput(self.container)
        self.input = ShellInput(
            on_submit=self._submit, classes="tab-shell-input", soft_wrap=True
        )

    def compose(self) -> ComposeResult:
        yield self.container
        yield self.input

    async def _submit(self, text: str, direct: bool, echo: str | None = None) -> None:
        self.submitted.append((text, echo))

    async def feed(self):
        for event in self.events:
            await self.output.view(event)
            self.input.set_secret(
                self.output.active_field_secret,
                self.output.active_field_value,
            )


@pytest.mark.asyncio
async def test_real_su_password_typing_is_masked_end_to_end():
    app = _RealShellHarness(await _real_su_password_events())
    async with app.run_test() as pilot:
        app.input.focus()
        await pilot.pause()

        await app.feed()
        await pilot.pause()

        assert app.output.active_field_secret is True
        assert app.input.secret is True

        await pilot.press(*"hunter2")
        assert app.input._raw == "hunter2"
        assert "hunter2" not in app.input.text
        assert MASK in app.input.text

        await pilot.press("enter")
        # raw value reaches the Command, echo never carries it
        assert app.submitted == [("hunter2", MASK * 7)]


@pytest.mark.asyncio
async def test_secret_submit_echo_never_renders_raw():
    """The ctx echo round-trip must not print the raw password."""
    raw = "hunter2"
    events = await _real_su_password_events()
    app = _RealShellHarness(events)
    async with app.run_test() as pilot:
        app.input.focus()
        await pilot.pause()
        await app.feed()
        await pilot.pause()

        await pilot.press(*raw)
        await pilot.press("enter")
        (_, echo) = app.submitted[0]
        assert raw not in echo

        # the response document echoes ctx back — with the masked echo
        from y5n.runtime.api.document.transfer import DocumentEvent

        response = DocumentEvent(ctx=InputContext(echo=echo), job_id="test:su")
        await app.output.view(response)
        await pilot.pause()

        rendered = []
        for static in app.query("Vertical.document-group CopyableStatic"):
            content = static.content
            rendered.append(content.plain if hasattr(content, "plain") else str(content))
        text = "\n".join(rendered)
        assert raw not in text
