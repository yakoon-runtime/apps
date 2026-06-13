from __future__ import annotations

from collections.abc import Awaitable, Callable

from textual import events
from textual.widgets import TextArea


class ShellInput(TextArea):

    def __init__(self, on_submit: Callable[[str], Awaitable[None]], **kwargs):
        super().__init__(**kwargs)
        self._on_submit = on_submit

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.clear()
                await self._on_submit(text)
        elif event.key != "enter" and "enter" in event.key:
            event.stop()
            self.insert("\n")
        elif "ctrl+j" in event.aliases or "newline" in event.aliases:
            event.stop()
            self.insert("\n")
        else:
            await super()._on_key(event)
