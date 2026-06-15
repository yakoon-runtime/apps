from __future__ import annotations

from pathlib import Path

import yaml
from y5n.base.theme import ThemeManager, default_themes
from y5ntrans.websocket.client import WebSocketClientTransport

import textual.theme as textual_theme
from textual import events
from textual.app import App, ComposeResult
from textual.theme import Theme as TextualTheme
from textual.widgets import Static, TabbedContent

from .conf import TextureConfig
from .tab import RuntimeTab

_THEME_MANAGER = ThemeManager(default_themes())


def _to_textual(name: str) -> str | None:
    theme = _THEME_MANAGER.get(name)
    if not theme:
        return None
    textual_theme.BUILTIN_THEMES[name] = TextualTheme(
        name=name,
        primary=theme.primary,
        secondary=theme.secondary,
        accent=theme.accent,
        warning=theme.warning,
        error=theme.error,
        success=theme.success,
        foreground=theme.text,
        background=theme.bg,
        surface=theme.surface,
        variables={"font": theme.font},
    )
    return name


class TextualApp(App):

    CSS_PATH = Path(__file__).parent / "terminal.tcss"

    def __init__(
        self,
        config: TextureConfig,
        config_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._tabs: list[RuntimeTab] = []
        self._active_tab: int = 0
        self._tab_counter: int = 0
        self._tabs_container: TabbedContent | None = None
        self._status_bar_text: Static | None = None
        if config.theme:
            resolved = _to_textual(config.theme)
            if resolved is not None:
                self.theme = resolved

    # ── Compose ──

    def compose(self) -> ComposeResult:
        self._tabs_container = TabbedContent()
        yield self._tabs_container

        self._status_bar_text = Static("CTRL+Q  Quit |", id="status-bar")
        yield self._status_bar_text

    async def on_mount(self) -> None:
        for entry in self._config.runtimes:
            tab = await self._create_tab(entry.name)
            if entry.autoconnect:
                await self._try_connect(tab, entry.url)

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        if self._config_path is None or old_theme == new_theme:
            return
        try:
            with open(self._config_path) as f:
                data = yaml.safe_load(f) or {}
            data["theme"] = new_theme
            with open(self._config_path, "w") as f:
                yaml.dump(data, f)
        except Exception:
            pass

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
