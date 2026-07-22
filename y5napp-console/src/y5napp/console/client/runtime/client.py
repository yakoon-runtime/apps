import asyncio

from y5n.runtime.engine.runtime import Event
from y5n.runtime.engine.transport import Transport

from ..output import ConsoleOutput
from ..terminal import Terminal


class Client:

    SHELL_PROMPT = "shell$ "

    def __init__(self, transport: Transport):
        self.transport = transport

    async def run(self, terminal: Terminal):

        # ------------------------
        # View Handling
        # ------------------------

        async def on_view(event):
            await renderer.view(event)

        def on_stream_finished():
            terminal.set_prompt(self.SHELL_PROMPT)

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
            await connection.dispatch(Event.from_raw(text))

        terminal.on_input = on_input
        terminal.set_prompt(self.SHELL_PROMPT)

        # ------------------------
        # Start
        # ------------------------

        asyncio.create_task(renderer.run())
        await terminal.run()
