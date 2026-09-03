from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from textual import events
from textual.widgets import TextArea
from y5n.runtime.api.flow.patterns.public import FormAction

MASK = "\u2022"


class ShellInput(TextArea):

    BINDINGS = [
        ("ctrl+v", "paste", "Paste"),
        ("ctrl+n", "submit_form", "Next Required"),
        ("pageup", "scroll_page_up", "Scroll Up"),
        ("pagedown", "scroll_page_down", "Scroll Down"),
    ]

    def __init__(
        self,
        on_submit: Callable[[str, bool, str | None], Awaitable[None]],
        on_action: Callable[[FormAction], Awaitable[None]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._on_submit = on_submit
        self._on_action = on_action
        self._secret = False
        self._raw = ""

    # ── Secret mode (presentation only — the raw value is preserved) ──

    @property
    def secret(self) -> bool:
        return self._secret

    def set_secret(self, secret: bool, value: str | None = None) -> None:
        if secret:
            value = value or ""
            if self._secret and self._raw == value:
                return
            self._secret = True
            self._raw = value
            self.text = MASK * len(self._raw)
            self.cursor_location = self.document.end
        else:
            if self._secret:
                self._secret = False
                self._raw = ""
                self.text = ""
            if value is not None:
                self.text = value

    def submit_value(self) -> str:
        return (self._raw if self._secret else self.text).strip()

    def _redraw_masked(self) -> None:
        self.text = MASK * len(self._raw)
        self.cursor_location = self.document.end

    def clear(self) -> None:
        # Clearing ends the current input acquisition: secret presentation
        # state belongs to the active input only. A later secret Field
        # projection re-establishes it.
        self._secret = False
        self._raw = ""
        super().clear()

    async def action_submit_form(self) -> None:
        if self._on_action:
            self.clear()
            await self._on_action(FormAction("submit"))

    def action_paste(self) -> None:
        text = self.app.clipboard
        if text:
            if self._secret:
                self._raw += text
                self._redraw_masked()
            else:
                self.insert(text)

    def action_scroll_page_up(self) -> None:
        self._scroll_output_page(-1)

    def action_scroll_page_down(self) -> None:
        self._scroll_output_page(1)

    def _watch_has_focus(self, focus: bool) -> None:
        self._cursor_visible = True
        if focus:
            self._restart_blink()
            self.app.cursor_position = self.cursor_screen_offset
            self.history.checkpoint()
        else:
            self._pause_blink(visible=True)

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.clear()
            await self._on_submit("/jobs/bg", True, None)
        elif event.key == "enter":
            event.stop()
            event.prevent_default()
            text = self.submit_value()
            # Secret input never travels as raw echo — the renderer shows a
            # masked representation instead.
            echo = MASK * len(text) if self._secret else text
            self.clear()
            await self._on_submit(text, False, echo)
        elif event.key == "ctrl+up" and self._on_action:
            event.stop()
            event.prevent_default()
            await self._on_action(FormAction("previous"))
        elif event.key == "ctrl+down" and self._on_action:
            event.stop()
            event.prevent_default()
            await self._on_action(FormAction("next"))
        elif event.key == "ctrl+x":
            event.stop()
            event.prevent_default()
            self.clear()
            await self._on_submit("/jobs/stop --current", True, None)
        elif self._secret and event.is_printable:
            # Secret mode: capture the raw character, never echo it.
            event.stop()
            event.prevent_default()
            self._raw += event.character
            self._redraw_masked()
        elif self._secret and event.key == "backspace":
            event.stop()
            event.prevent_default()
            if self._raw:
                self._raw = self._raw[:-1]
                self._redraw_masked()
        else:
            await super()._on_key(event)

    def _scroll_output_page(self, direction: int) -> None:
        try:
            output = self.app.query_one(".tab-output")
            if direction < 0:
                output.scroll_page_up(animate=False)
            else:
                output.scroll_page_down(animate=False)
        except Exception:
            pass
