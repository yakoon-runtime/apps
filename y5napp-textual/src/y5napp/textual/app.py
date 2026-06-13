from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from y5ntrans.websocket.client import WebSocketClientTransport

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from .tab import RuntimeTab


@dataclass
class RuntimeConfig:
    name: str
    url: str
    autoconnect: bool = True


class TextualApp(App):

    CSS_PATH = Path(__file__).parent / "terminal.tcss"

    def __init__(self, configs: list[RuntimeConfig]) -> None:
        super().__init__()
        self._configs = configs
        self._tabs: list[RuntimeTab] = []
        self._active_tab: int = 0
        self._tab_bar: Horizontal | None = None
        self._output_container: Vertical | None = None
        self._status_bar_text: Static | None = None

    # ── Compose ──

    def compose(self) -> ComposeResult:
        self._tab_bar = Horizontal(id="tab-bar")
        yield self._tab_bar

        self._output_container = Vertical(id="output-container")
        yield self._output_container

        self._status_bar_text = Static("CTRL+Q  Quit |", id="status-bar")
        yield self._status_bar_text

    async def on_mount(self) -> None:
        for cfg in self._configs:
            try:
                await self._connect_runtime(cfg.name, cfg.url)
            except Exception:
                if cfg.autoconnect:
                    self._show_error_tab(cfg.name, f"Connection failed: {cfg.url}")

    # ── Tab Management ──

    async def _connect_runtime(self, name: str, url: str) -> None:
        transport = WebSocketClientTransport(url)
        await self._create_tab(name, transport)

    async def _create_tab(
        self, name: str, transport: WebSocketClientTransport
    ) -> RuntimeTab:
        tab = RuntimeTab(
            name=name,
            on_connect=self._on_connect,
            on_disconnect=self._close_tab,
        )
        assert self._output_container is not None
        self._output_container.mount(tab.container)
        tab.build()

        await tab.connect(transport)

        self._tabs.append(tab)
        self._rebuild_tab_bar()

        return tab

    def _show_error_tab(self, name: str, message: str) -> None:
        tab = RuntimeTab(
            name=name,
            on_connect=self._on_connect,
            on_disconnect=self._close_tab,
        )
        assert self._output_container is not None
        self._output_container.mount(tab.container)
        tab.build()
        tab.show_error(message)

        self._tabs.append(tab)
        self._rebuild_tab_bar()

    def _close_tab(self, tab: RuntimeTab) -> None:
        if len(self._tabs) <= 1:
            return

        try:
            idx = self._tabs.index(tab)
        except ValueError:
            return

        self._tabs.pop(idx)
        tab.container.remove()

        target = min(idx, len(self._tabs) - 1)
        self._rebuild_tab_bar()
        self._set_active_tab(target)

    # ── Tab Bar ──

    def _rebuild_tab_bar(self) -> None:
        if self._tab_bar is None:
            return
        self._tab_bar.query("Button").remove()
        for i, tab in enumerate(self._tabs):
            label = f"[b]{tab.name}[/b]" if i == self._active_tab else tab.name
            self._tab_bar.mount(Button(label))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._tab_bar is None:
            return
        for i, btn in enumerate(self._tab_bar.query("Button")):
            if btn is event.button:
                self._set_active_tab(i)
                break

    def _set_active_tab(self, index: int) -> None:
        self._active_tab = index

        for i, tab in enumerate(self._tabs):
            tab.container.display = i == index

        self._rebuild_tab_bar()

        tab = self._tabs[index]
        tab.focus_input()

    # ── Connect Callback ──

    async def _on_connect(self, name: str, url: str) -> None:
        await self._connect_runtime(name, url)
        self._set_active_tab(len(self._tabs) - 1)

    # ── Resize ──

    def on_resize(self, event: events.Resize) -> None:
        if self._status_bar_text is not None:
            if self._tabs:
                tab = self._tabs[self._active_tab]
                info = tab.connection.runtime_info if tab.connection else None
                self._status_bar_text.update(
                    f"CTRL+Q  Quit  |  {info.version if info else ''}"
                )
            else:
                self._status_bar_text.update("CTRL+Q  Quit  |  no runtimes connected")
