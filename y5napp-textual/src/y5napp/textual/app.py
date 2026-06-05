from __future__ import annotations

from pathlib import Path

from y5n.base.clients import ClientConnection
from y5n.base.projection import ProjectionEvent
from y5n.base.runtime import InputEvent
from y5n.base.runtime.input import InputContext
from y5n.runtime.machine import RuntimeHost
from y5n.runtime.settings import Settings
from y5n.runtime.transport import LocalTransport
from y5n.runtime.wire.runtime import build_runtime

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, TextArea

from .output import TextualOutput


class TextualApp(App):

    CSS_PATH = Path(__file__).parent / "terminal.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.scroll_area: Vertical | None = None
        self.input_widget: TextArea | None = None
        self._status_line: Static | None = None
        self._output_handler: TextualOutput | None = None
        self._connection: ClientConnection | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="output"):
            self.scroll_area = Vertical(id="scroll-area")
            yield self.scroll_area

            with Vertical(classes="input-card"):
                self.input_widget = TextArea(
                    "",
                    id="shell-input",
                    soft_wrap=True,
                )
                yield self.input_widget
                self._status_line = Static(
                    "? · ~ $",
                    id="status-line",
                )
                yield self._status_line

    async def on_mount(self) -> None:
        self._output_handler = TextualOutput(self.scroll_area)

        host = await self._create_runtime()
        await host.setup()

        transport = LocalTransport(host)
        self._connection = await transport.connect(self._on_view)

    async def _create_runtime(self) -> RuntimeHost:
        settings = Settings()
        return build_runtime(
            settings=settings,
            plugins=[
                "y5nspace.shell",
                "y5nspace.ident",
                "y5nspace.runtime",
            ],
            capabilities={},
        )

    async def _on_view(self, event: ProjectionEvent) -> None:
        if self._output_handler is not None:
            await self._output_handler.view(event)

        if self._status_line is not None:
            try:
                user = event.state.user if event.state and event.state.user else "?"
                path = (
                    event.state.node_path if event.state and event.state.node_path else "~"
                )
                self._status_line.update(f"{user} · {path} $")
            except Exception:
                pass

    BINDINGS = [("ctrl+enter", "submit", "Submit")]

    async def action_submit(self) -> None:
        assert self.input_widget
        text = self.input_widget.text.strip()
        self.input_widget.clear()

        if not text:
            return

        if self._connection is not None:
            await self._connection.dispatch(
                InputEvent.from_raw(
                    text,
                    context=InputContext(origin=text),
                )
            )
