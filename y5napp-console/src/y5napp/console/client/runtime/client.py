import asyncio

from y5n.base.projection import ProjectionEvent, ProjectionQuery
from y5n.base.runtime import Event
from y5n.base.transport import Transport

from ..output import ConsoleOutput
from ..terminal import Terminal


class Client:

    SHELL_PROMPT = "shell$ "

    def __init__(self, transport: Transport):
        self.transport = transport

        self._current_fields = []
        self._current_index = 0
        self._current_values = {}

        self.query = ProjectionQuery()

    async def run(self, terminal: Terminal):

        # ------------------------
        # View Handling
        # ------------------------

        async def on_view(event: ProjectionEvent):

            self.query.apply(event)
            await renderer.view(event)

        def on_stream_finished():
            self._handle_view_ready(terminal)

        renderer = ConsoleOutput(terminal)
        renderer.on_finished = on_stream_finished

        # ------------------------
        # Connection
        # ------------------------

        connection = await self.transport.connect(on_view)

        # ------------------------
        # Input Handling
        # ------------------------

        async def on_input(text: str):

            if not text:
                terminal.set_prompt(self.SHELL_PROMPT)

            if not self._current_fields:
                await connection.dispatch(Event.from_raw(text))
                return

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

            event = Event(payload="debug")
            await connection.dispatch(event)

        terminal.on_input = on_input
        terminal.set_prompt(self.SHELL_PROMPT)

        # ------------------------
        # Start
        # ------------------------

        asyncio.create_task(renderer.run())
        await terminal.run()

    # --------------------------------------------------------

    def _handle_view_ready(self, terminal: Terminal):

        self._reset_form()
        terminal.set_prompt(self.SHELL_PROMPT)

        if not self.query.expects_input():
            return

        self._current_fields = self.query.fields()
        self._current_index = 0
        self._current_values = {}

        if not self._current_fields:
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
