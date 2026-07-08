from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from y5n.base.flow.patterns.public import FormAction

from textual import events
from textual.widgets import TextArea


class ShellInput(TextArea):

    BINDINGS = [
        ("ctrl+v", "paste", "Paste"),
    ]

    def __init__(
        self,
        on_submit: Callable[[str], Awaitable[None]],
        on_action: Callable[[FormAction], Awaitable[None]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._on_submit = on_submit
        self._on_action = on_action

    def action_paste(self) -> None:
        text = self.app.clipboard
        if text:
            self.insert(text)

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.clear()
            await self._on_submit("bg")
        elif event.key == "enter":
            event.stop()
            event.prevent_default()
            text = self.text.strip()
            self.clear()
            await self._on_submit(text)
        elif event.key != "enter" and "enter" in event.key:
            event.stop()
            self.insert("\n")
        elif "ctrl+j" in event.aliases or "newline" in event.aliases:
            event.stop()
            self.insert("\n")
        elif event.key == "ctrl+up" and self._on_action:
            event.stop()
            event.prevent_default()
            await self._on_action(FormAction("previous"))
        elif event.key == "ctrl+down" and self._on_action:
            event.stop()
            event.prevent_default()
            await self._on_action(FormAction("next"))
        else:
            await super()._on_key(event)
