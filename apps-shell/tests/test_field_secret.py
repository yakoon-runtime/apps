"""Field.secret in the Shell renderer: detection, masking, mode reset.

The Shell honors the projection's field ``secret`` property by not
visibly echoing entered characters — the raw value still reaches the
submitted event unchanged. Ordinary fields behave exactly as before;
secret state never leaks into a later ordinary field.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static
from y5n.apps.shell.input import MASK, ShellInput
from y5n.apps.shell.output import CopyableStatic, TextualOutput


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

    async def _submit(self, text: str, direct: bool) -> None:
        self.submitted.append((text, direct))


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
        assert app.submitted == [("hunter2", False)]  # raw value reaches submit
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
        assert app.submitted == [("hello", False)]


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
