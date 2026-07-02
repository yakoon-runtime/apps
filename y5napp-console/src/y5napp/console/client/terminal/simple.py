import asyncio
import sys

from .base import Terminal


class SimpleTerminal(Terminal):

    def __init__(self):
        self._running = True

    async def run(self):

        while self._running:

            try:
                line = await asyncio.to_thread(sys.stdin.readline)
            except KeyboardInterrupt:
                await self.stop()
                return

            if not line:
                await self.stop()
                return

            line = line.strip()
            await self.on_input(line)

    async def stop(self):
        self._running = False

    async def on_input(self, text):
        pass

    def write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def new_line(self):
        sys.stdout.write("\n")
        sys.stdout.flush()

    def set_prompt(self, text: str):
        sys.stdout.write(text)
        sys.stdout.flush()
