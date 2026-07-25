import asyncio

from .base import Terminal


class SSHTerminal(Terminal):

    def __init__(self, stdin, stdout):
        self.stdin = stdin
        self.stdout = stdout

        self._running = True
        self._buffer = ""

    # ------------------------
    # Lifecycle
    # ------------------------

    def data_received(self, data, datatype):
        self._buffer += data

        # Input lesen
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)

            line = line.strip()
            asyncio.create_task(self.on_input(line))

    # ------------------------
    # Terminal API
    # ------------------------

    async def run(self):
        self._done = asyncio.Event()
        await self._done.wait()

    async def stop(self):
        self._running = False
        self._done.set()
        self.stdout.close()

    async def on_input(self, text):
        """Wird vom Client gesetzt"""
        pass

    def write(self, text: str):
        self.stdout.write(text)

    def new_line(self):
        self.stdout.write("\n")

    def set_prompt(self, text: str):
        self.write(text)
