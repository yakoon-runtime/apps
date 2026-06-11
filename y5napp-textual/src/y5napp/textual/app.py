from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from y5n.base.clients import ClientConnection
from y5n.base.projection import ProjectionEvent
from y5n.base.runtime import Event
from y5n.base.runtime.input import InputContext
from y5n.runtime.machine import RuntimeHost
from y5n.runtime.settings import Settings
from y5n.runtime.transport import LocalTransport
from y5n.runtime.wire.runtime import build_runtime
from y5ntrans.websocket.client import WebSocketClientTransport

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static, TextArea

from .output import TextualOutput


@dataclass
class RuntimeTab:
    name: str
    connection: Optional[ClientConnection]
    output: TextualOutput
    container: Vertical
    status_prefix: str = "space:"
    status_path: str = "/$"


class ShellInput(TextArea):

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if not self.text.strip():
                return
            app = self.app
            if isinstance(app, TextualApp):
                await app.action_submit()
        elif event.key != "enter" and "enter" in event.key:
            event.stop()
            self.insert("\n")
        elif "ctrl+j" in event.aliases or "newline" in event.aliases:
            event.stop()
            self.insert("\n")
        else:
            await super()._on_key(event)


class TextualApp(App):

    CSS_PATH = Path(__file__).parent / "terminal.tcss"

    def __init__(self) -> None:
        super().__init__()
        self._tabs: list[RuntimeTab] = []
        self._active_tab: int = 0
        self._tab_bar: Horizontal | None = None
        self._output_container: Vertical | None = None
        self.input_widget: ShellInput | None = None
        self._status_brand: Static | None = None
        self._status_prefix: Static | None = None
        self._status_path: Static | None = None
        self._status_bar_text: Static | None = None

    def compose(self) -> ComposeResult:
        self._tab_bar = Horizontal(id="tab-bar")
        yield self._tab_bar

        self._output_container = Vertical(id="output-container")
        yield self._output_container

        with Vertical(classes="input-card"):
            self.input_widget = ShellInput(
                "",
                id="shell-input",
                soft_wrap=True,
            )
            yield self.input_widget
            with Horizontal(id="status-line"):
                self._status_brand = Static("yakoon", classes="brand")
                yield self._status_brand
                yield Static(" · ", classes="sep")
                self._status_prefix = Static("space:", classes="prefix")
                yield self._status_prefix
                self._status_path = Static("/$", classes="path")
                yield self._status_path

        self._status_bar_text = Static("CTRL+Q  Quit |", id="status-bar")
        yield self._status_bar_text

    async def on_mount(self) -> None:
        await self._add_local_tab()

    # --------------------------------------------------------
    # Tabs
    # --------------------------------------------------------

    async def _add_local_tab(self) -> None:
        host = await self._create_runtime()
        await host.setup()

        transport = LocalTransport(host)
        tab = await self._create_tab("local", transport)
        self.action_activate_tab(len(self._tabs) - 1)

        if tab.connection.runtime_info and self._status_bar_text is not None:
            self._update_status_bar(
                tab.connection.runtime_info.version, self.size.width
            )

    async def _create_tab(
        self, name: str, transport: LocalTransport | WebSocketClientTransport
    ) -> RuntimeTab:
        container = Vertical(classes="tab-output")
        self._output_container.mount(container)

        output = TextualOutput(container)
        tab = RuntimeTab(name=name, connection=None, output=output, container=container)

        connection = await transport.connect(self._make_view_callback(tab))
        tab.connection = connection

        self._tabs.append(tab)
        self._rebuild_tab_bar()

        return tab

    def _make_view_callback(self, tab: RuntimeTab):
        async def on_view(event: ProjectionEvent) -> None:
            await tab.output.view(event)

            if self._tabs and self._tabs[self._active_tab] is tab:
                self._update_status_from_event(event)

        return on_view

    async def _connect_remote(self, url: str) -> None:
        transport = WebSocketClientTransport(url)
        tab = await self._create_tab(url, transport)
        self.action_activate_tab(len(self._tabs) - 1)

    def _close_active_tab(self) -> None:
        if len(self._tabs) <= 1:
            return

        tab = self._tabs.pop(self._active_tab)
        tab.container.remove()

        target = min(self._active_tab, len(self._tabs) - 1)
        self._rebuild_tab_bar()
        self.action_activate_tab(target)

    def _rebuild_tab_bar(self) -> None:
        if self._tab_bar is None:
            return
        self._tab_bar.query("Button").remove()
        for i, tab in enumerate(self._tabs):
            label = tab.name
            if i == self._active_tab:
                label = f"[b]{label}[/b]"
            btn = Button(label, action=f"activate_tab({i})")
            self._tab_bar.mount(btn)

    def action_activate_tab(self, index: int) -> None:
        self._active_tab = index

        for i, tab in enumerate(self._tabs):
            tab.container.display = i == index

        self._rebuild_tab_bar()

        active = self._tabs[index]
        self._status_prefix.update(active.status_prefix)
        self._status_path.update(active.status_path)

    # --------------------------------------------------------
    # Runtime
    # --------------------------------------------------------

    async def _create_runtime(self) -> RuntimeHost:
        settings = Settings()
        return build_runtime(
            settings=settings,
            plugins=[
                "y5nspace.shell",
                "y5nspace.ident",
                "y5nspace.runtime",
                "y5nspace.os",
            ],
            capabilities={},
        )

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    async def action_submit(self) -> None:
        assert self.input_widget
        text = self.input_widget.text.strip()
        self.input_widget.clear()

        if not text:
            return

        if text.startswith("/connect "):
            url = text[len("/connect "):].strip()
            await self._connect_remote(url)
            return

        if text == "/disconnect":
            self._close_active_tab()
            return

        active = self._tabs[self._active_tab]
        if active.connection is not None:
            await active.connection.dispatch(
                Event.from_raw(
                    text,
                    context=InputContext(origin=text),
                )
            )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    def _update_status_from_event(self, event: ProjectionEvent) -> None:
        if self._status_prefix is not None:
            try:
                path = (
                    event.state.node_path
                    if event.state and event.state.node_path
                    else "/"
                )
                self._status_prefix.update(
                    f"{event.state.user}@space:"
                    if event.state and event.state.user
                    else "space:"
                )
                self._status_path.update(f"{path}$")

                tab = self._tabs[self._active_tab]
                tab.status_prefix = str(self._status_prefix.renderable)
                tab.status_path = str(self._status_path.renderable)
            except Exception:
                pass

    def _update_status_bar(self, ver: str, width: int) -> None:
        left = "CTRL+Q  Quit  |"
        right = f"v{ver}"
        pad = max(0, width - len(left) - len(right) - 3)
        if self._status_bar_text is not None:
            self._status_bar_text.update(f"{left}{' ' * pad}{right}")

    def on_resize(self, event: events.Resize) -> None:
        if self._tabs and self._status_bar_text is not None:
            tab = self._tabs[self._active_tab]
            info = tab.connection.runtime_info if tab.connection else None
            if info:
                self._update_status_bar(info.version, event.size.width)
