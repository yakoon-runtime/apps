from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from y5ntrans.websocket.client import WebSocketClientTransport

from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Static, TabbedContent

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
        self._tab_counter: int = 0
        self._tabs_container: TabbedContent | None = None
        self._status_bar_text: Static | None = None

    # ── Compose ──

    def compose(self) -> ComposeResult:
        self._tabs_container = TabbedContent()
        yield self._tabs_container

        self._status_bar_text = Static("CTRL+Q  Quit |", id="status-bar")
        yield self._status_bar_text

    async def on_mount(self) -> None:
        for cfg in self._configs:
            tab = await self._create_tab(cfg.name)
            if cfg.autoconnect:
                await self._try_connect(tab, cfg.url)

    # ── Tab Management ──

    async def _create_tab(self, name: str) -> RuntimeTab:
        pane_id = f"tab-{self._tab_counter}"
        self._tab_counter += 1

        tab = RuntimeTab(
            name=name,
            pane_id=pane_id,
            on_connect=self._on_connect,
            on_disconnect=self._close_tab,
        )
        assert self._tabs_container is not None
        await self._tabs_container.add_pane(tab.pane)
        self._tabs_container.active = pane_id

        tab.build()

        self._tabs.append(tab)
        self._active_tab = len(self._tabs) - 1

        return tab

    async def _try_connect(self, tab: RuntimeTab, url: str) -> None:
        try:
            transport = WebSocketClientTransport(url)
            await tab.connect(transport)
        except Exception:
            tab._show_disconnected("Connection failed")

    async def _close_tab(self, tab: RuntimeTab) -> None:
        if len(self._tabs) <= 1:
            return

        try:
            idx = self._tabs.index(tab)
        except ValueError:
            return

        self._tabs.pop(idx)
        assert self._tabs_container is not None
        await self._tabs_container.remove_pane(tab.pane_id)

        self._active_tab = min(idx, len(self._tabs) - 1)

    # ── Tab Activated ──

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        pane_id = event.pane.id if event.pane else None
        if pane_id is None:
            return
        for i, tab in enumerate(self._tabs):
            if tab.pane_id == pane_id:
                self._active_tab = i
                tab.focus_input()
                break

    # ── Connect Callback ──

    async def _on_connect(self, name: str, url: str) -> None:
        tab = await self._create_tab(name)
        await self._try_connect(tab, url)

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
