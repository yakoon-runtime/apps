from .base import Terminal


class SSHTerminal(Terminal):

    def __init__(self, stdin, stdout):
        self.stdin = stdin
        self.stdout = stdout
        self._running = True

        self.on_input = None  # wird vom Client gesetzt

    # ------------------------
    # Lifecycle
    # ------------------------

    async def run(self):
        while self._running:
            line = await self.stdin.readline()
            if not line:
                break

            text = line.strip()

            if self.on_input:
                await self.on_input(text)

    async def stop(self):
        self._running = False

    # ------------------------
    # Terminal API
    # ------------------------

    def write(self, text: str):
        self.stdout.write(text)

    def new_line(self):
        self.stdout.write("\n")

    def notify_ready(self):
        pass  # optional

    # ------------------------
    # Prompt
    # ------------------------

    def set_prompt(self, field):
        # minimal: ignorieren oder später erweitern
        pass

    def reset_prompt(self):
        self.write("shell$ ")
