import asyncio
import sys

from .base import Terminal


class SimpleTerminal(Terminal):

    def __init__(self):
        self._running = True
        self._ready = asyncio.Event()
        self._ready.set()

    async def run(self):

        while self._running:

            # Warten bis Output fertig ist
            self._ready.clear()

            # Prompt anzeigen
            self.reset_prompt()

            # Input lesen
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line.strip():
                continue

            await self.on_input(line.strip())
            await self._ready.wait()

    def notify_ready(self):
        self._ready.set()

    async def stop(self):
        self._running = False

    def write(self, text):
        sys.stdout.write(text)

    def new_line(self):
        sys.stdout.write("\n")
        sys.stdout.flush()

    def set_prompt(self, field):
        print(f"{field.name}: ", end="", flush=True)

    def reset_prompt(self):
        sys.stdout.write("shell$ ")
        sys.stdout.flush()

    # wird vom Client gesetzt
    async def on_input(self, text):
        pass
