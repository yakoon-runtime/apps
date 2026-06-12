from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from y5n.base.clients import ClientConnection
from y5n.base.projection import ProjectionEvent
from y5n.base.runtime import Event
from y5n.base.runtime.input import InputContext
from y5ntrans.websocket.client import WebSocketClientTransport

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static, TextArea

from .output import TextualOutput


@dataclass
class RuntimeConfig:
    name: str
    url: str
    autoconnect: bool = True


@dataclass
class RuntimeTab:
    name: str
    connection: ClientConnection | None
    output: TextualOutput
    container: Vertical
    status_prefix: str = "space:"
    status_path: str = "/$"


def _load_config() -> list[RuntimeConfig]:
    paths = TextualApp._config_paths()
    for p in paths:
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f)
            if not data or "runtimes" not in data:
                return []
            return [
                RuntimeConfig(
                    name=r.get("name", r["url"]),
                    url=r["url"],
                    autoconnect=r.get("autoconnect", True),
                )
                for r in data["runtimes"]
            ]
    return []


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
        configs = _load_config()
        for i, cfg in enumerate(configs):
            try:
                await self._connect_runtime(cfg.name, cfg.url)
            except Exception:
                if cfg.autoconnect:
                    self._show_error_tab(cfg.name, f"Connection failed: {cfg.url}")

    # --------------------------------------------------------
    # Config
    # --------------------------------------------------------

    @staticmethod
    def _config_paths() -> list[Path]:
        return [
            Path.cwd() / "texture.yaml",
            Path("~/.config/y5n/texture.yaml").expanduser(),
        ]

    # --------------------------------------------------------
    # Tabs
    # --------------------------------------------------------

    def _show_error_tab(self, name: str, message: str) -> None:
        container = Vertical(classes="tab-output")
        self._output_container.mount(container)
        output = TextualOutput(container)
        tab = RuntimeTab(name=name, connection=None, output=output, container=container)
        self._tabs.append(tab)
        self._rebuild_tab_bar()
        from rich.text import Text

        container.mount(Static(Text(f"[!] {message}", style="red")))

    async def _connect_runtime(self, name: str, url: str) -> None:
        transport = WebSocketClientTransport(url)
        await self._create_tab(name, transport)

    async def _create_tab(
        self, name: str, transport: WebSocketClientTransport
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
            if event.view_params:
                connect_url = event.view_params.get("connect")
                if connect_url:
                    name = event.view_params.get("connect_name", connect_url)
                    await self._connect_runtime(name, connect_url)
                    self._set_active_tab(len(self._tabs) - 1)
                    return

            await tab.output.view(event)

            if self._tabs and self._tabs[self._active_tab] is tab:
                self._update_status_from_event(event)

        return on_view

    async def _connect_remote(self, url: str) -> None:
        try:
            await self._connect_runtime(url, url)
            self._set_active_tab(len(self._tabs) - 1)
        except Exception:
            self._show_error_tab(url, f"Connection failed: {url}")

    def _close_active_tab(self) -> None:
        if len(self._tabs) <= 1:
            return

        tab = self._tabs.pop(self._active_tab)
        tab.container.remove()

        target = min(self._active_tab, len(self._tabs) - 1)
        self._rebuild_tab_bar()
        self._set_active_tab(target)

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

        active = self._tabs[index]
        self._status_prefix.update(active.status_prefix)
        self._status_path.update(active.status_path)

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
            url = text[len("/connect ") :].strip()
            await self._connect_remote(url)
            return

        if text == "/disconnect":
            self._close_active_tab()
            return

        if not self._tabs:
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
