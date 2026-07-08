from __future__ import annotations

from collections.abc import Awaitable, Callable

from y5n.base.clients import ClientConnection
from y5n.base.flow.patterns.public import FormAction
from y5n.base.projection import ProjectionEvent
from y5n.base.runtime import Event
from y5n.base.runtime.input import InputContext, Origin
from y5ntrans.websocket.client import WebSocketClientTransport

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static, TabPane

from .input import ShellInput
from .output import TextualOutput


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
        self._url: str | None = None
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._built = False

        # ── Pane (attached by app before build) ──
        self.pane = TabPane(title=name, id=pane_id)

        # ── Widgets (created, not yet mounted) ──
        self._output_container = VerticalScroll(classes="tab-output")
        self.output = TextualOutput(self._output_container)

        self._input = ShellInput(
            on_submit=self._handle_submit,
            on_action=self._handle_action,
            classes="tab-shell-input",
            soft_wrap=True,
        )

        self._status_brand = Static("Yakoon", classes="brand")
        self._status_sep = Static(" · ", classes="sep")
        self._status_prefix = Static(f"{name}:", classes="prefix")
        self._status_path = Static("/$", classes="path")
        self._error_widgets: list[Widget] = []

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

        if text == "/reconnect":
            await self._reconnect()
            return

        if self.connection is not None:
            try:
                await self.connection.dispatch(
                    Event.from_raw(
                        text,
                        context=InputContext(
                            origin=Origin.HUMAN,
                            channel="textual",
                            echo=text,
                        ),
                    )
                )
            except Exception:
                self.connection = None
                self._show_disconnected()

    # ── Connection ──

    async def connect(self, transport: WebSocketClientTransport) -> None:
        self._url = transport._url
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

                if event.view_params.get("clear"):
                    self._clear_errors()

            await self.output.view(event)
            self.update_status(event)
            self._sync_input_with_form()

        return on_view

    def _clear_errors(self) -> None:
        for w in self._error_widgets:
            w.remove()
        self._error_widgets.clear()

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
        w = Static(message, classes="error-message")
        self._output_container.mount(w)
        self._error_widgets.append(w)

    def _show_disconnected(self, message: str = "Connection lost") -> None:
        w = Static(f"{message}\n  /reconnect to retry", classes="error-message")
        self._output_container.mount(w)
        self._error_widgets.append(w)

    async def _reconnect(self) -> None:
        if self._url is None:
            return
        self._clear_errors()

        transport = WebSocketClientTransport(self._url)
        try:
            await self.connect(transport)
            w = Static("Reconnected", classes="success-message")
            self._output_container.mount(w)
            self._error_widgets.append(w)
        except Exception:
            self._show_disconnected()

    # ── Form actions ──

    async def _handle_action(self, action: FormAction) -> None:
        if self.connection is not None:
            self._input.clear()
            try:
                await self.connection.dispatch(
                    Event(
                        payload=action,
                        context=InputContext(
                            origin=Origin.HUMAN,
                            channel="textual",
                        ),
                    )
                )
            except Exception:
                self.connection = None
                self._show_disconnected()

    # ── Form field support ──

    def _sync_input_with_form(self) -> None:
        value = self.output.active_field_value
        if value is not None:
            self._input.text = value

    # ── Focus ──

    def focus_input(self) -> None:
        self._input.focus()
