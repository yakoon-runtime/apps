import asyncio

from yakoon.base.projection import ProjectionEvent, ProjectionQuery
from yakoon.base.runtime import InputEvent
from yakoon.base.transports import Transport

from ..output import ConsoleOutput
from ..terminal import SimpleTerminal


class ConsoleClient:

    def __init__(self, transport: Transport):
        self.transport = transport

        self._current_fields = []
        self._current_index = 0
        self._current_values = {}

        self.query = ProjectionQuery()

    async def run(self):

        # ------------------------
        # Setup
        # ------------------------

        # surface = TerminalSurface()
        terminal = SimpleTerminal()
        renderer = ConsoleOutput(terminal)

        # ------------------------
        # Input Handling
        # ------------------------

        async def on_input(text: str):

            # Command Mode
            if not self._current_fields:
                await connection.send_input(InputEvent.from_raw(text))
                return

            # Form Mode
            field = self._current_fields[self._current_index]

            self._current_values[field.name] = text
            self._current_index += 1

            if self._current_index < len(self._current_fields):
                self._show_next_prompt(terminal)
                return

            args = []
            for key, value in self._current_values.items():
                args.append(f"--{key}")
                args.append(str(value))

            event = InputEvent("debug", args)
            await connection.send_input(event)

        terminal.on_input = on_input

        # ------------------------
        # View Handling
        # ------------------------

        async def on_view(event: ProjectionEvent):

            self.query.apply(event)
            await renderer.view(event)

            if not event.is_final():
                return

            self._handle_view_ready(terminal)

        connection = await self.transport.connect(on_emit=on_view)

        # ------------------------
        # Start
        # ------------------------

        # terminal.reset_prompt()

        asyncio.create_task(renderer.run())
        await terminal.run()

    # --------------------------------------------------------

    def _handle_view_ready(self, terminal):

        self._reset_form()

        if not self.query.expects_input():
            # terminal.reset_prompt()
            return

        self._current_fields = self.query.fields()
        self._current_index = 0
        self._current_values = {}

        if not self._current_fields:
            # terminal.reset_prompt()
            return

        self._show_next_prompt(terminal)

    # --------------------------------------------------------

    def _show_next_prompt(self, terminal):

        if self._current_index >= len(self._current_fields):
            return

        field = self._current_fields[self._current_index]

        terminal.set_prompt(field)

    # --------------------------------------------------------

    def _reset_form(self):
        self._current_fields = []
        self._current_index = 0
        self._current_values = {}
