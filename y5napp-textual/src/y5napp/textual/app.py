from __future__ import annotations

from pathlib import Path

from y5n.base.clients import ClientConnection
from y5n.base.projection import ProjectionEvent
from y5n.base.runtime import InputEvent
from y5n.runtime.machine import RuntimeHost
from y5n.runtime.settings import Settings
from y5n.runtime.transport import LocalTransport
from y5n.runtime.wire.runtime import build_runtime

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Input

from .output import TextualOutput


class TextualApp(App):

    CSS_PATH = Path(__file__).parent / "terminal.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.output_container: Vertical | None = None
        self.input: Input | None = None
        self._output_handler: TextualOutput | None = None
        self._connection: ClientConnection | None = None

    def compose(self) -> ComposeResult:
        self.output_container = Vertical(id="output")
        self.input = Input(placeholder="shell$ ", id="shell-input")
        yield self.output_container
        yield self.input

    async def on_mount(self) -> None:
        self._output_handler = TextualOutput(self.output_container)

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

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        text = message.value

        assert self.input
        self.input.clear()

        if not text:
            return

        if self._connection is not None:
            await self._connection.dispatch(InputEvent.from_raw(text))
