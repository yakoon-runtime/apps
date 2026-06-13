from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from y5n.base.clients import ClientConnection
from y5n.base.projection import ProjectionEvent
from y5n.base.runtime import Event
from y5n.base.runtime.input import InputContext

from textual.containers import Horizontal, Vertical
from textual.widgets import Static, TabPane

from .input import ShellInput
from .output import TextualOutput

if TYPE_CHECKING:
    from y5ntrans.websocket.client import WebSocketClientTransport


class RuntimeTab:

    def __init__(
        self,
        name: str,
        pane_id: str,
        on_connect: Callable[[str, str], Awaitable[None]],
        on_disconnect: Callable[[RuntimeTab], Awaitable[None]],
    ):
        self.name = name
        self.pane_id = pane_id
        self.connection: ClientConnection | None = None
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._built = False

        # ── Pane (attached by app before build) ──
        self.pane = TabPane(title=name, id=pane_id)

        # ── Widgets (created, not yet mounted) ──
        self._output_container = Vertical(classes="tab-output")
        self.output = TextualOutput(self._output_container)

        self._input = ShellInput(
            on_submit=self._handle_submit,
            classes="tab-shell-input",
            soft_wrap=True,
        )

        self._status_brand = Static("Yakoon", classes="brand")
        self._status_sep = Static(" · ", classes="sep")
        self._status_prefix = Static(f"{name}:", classes="prefix")
        self._status_path = Static("/$", classes="path")

    # ── Build (call after pane is attached) ──

    def build(self) -> None:
        if self._built:
            return
        self._built = True

        self.pane.mount(self._output_container)

        input_card = Vertical(classes="input-card")
        self.pane.mount(input_card)

        input_card.mount(self._input)

        status_line = Horizontal(classes="tab-status-line")
        input_card.mount(status_line)
        status_line.mount(
            self._status_brand,
            self._status_sep,
            self._status_prefix,
            self._status_path,
        )

    # ── Submit ──

    async def _handle_submit(self, text: str) -> None:
        if text.startswith("/connect "):
            url = text[len("/connect ") :].strip()
            await self._on_connect(url, url)
            return

        if text == "/disconnect":
            await self._on_disconnect(self)
            return

        if self.connection is not None:
            await self.connection.dispatch(
                Event.from_raw(text, context=InputContext(origin=text))
            )

    # ── Connection ──

    async def connect(self, transport: WebSocketClientTransport) -> None:
        connection = await transport.connect(self._make_view_callback())
        self.connection = connection

    # ── View ──

    def _make_view_callback(self):
        async def on_view(event: ProjectionEvent) -> None:
            if event.view_params:
                connect_url = event.view_params.get("connect")
                if connect_url:
                    name = event.view_params.get("connect_name", connect_url)
                    await self._on_connect(name, connect_url)
                    return

            await self.output.view(event)
            self.update_status(event)

        return on_view

    def update_status(self, event: ProjectionEvent) -> None:
        try:
            path = (
                event.state.node_path if event.state and event.state.node_path else "/"
            )
            prefix = (
                f"{event.state.user}@{self.name}:"
                if event.state and event.state.user
                else f"{self.name}:"
            )
            self._status_prefix.update(prefix)
            self._status_path.update(f"{path}$")
        except Exception:
            pass

    # ── Error ──

    def show_error(self, message: str) -> None:
        from rich.text import Text

        self._output_container.mount(Static(Text(f"[!] {message}", style="red")))

    # ── Focus ──

    def focus_input(self) -> None:
        self._input.focus()
