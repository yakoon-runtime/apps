from yakoon.client.runtime import Client, create_runtime
from yakoon.client.terminal import PromptToolkitTerminal
from yakoon.client.terminal.simple import SimpleTerminal
from yakoon.platform.transport import LocalTransport


async def run() -> None:

    # Startup
    host = await create_runtime()
    transport = LocalTransport(host)
    # transport = WebSocketTransport("ws://localhost:8000/ws")

    terminal = SimpleTerminal()

    client = Client(transport)
    await client.run(terminal)

    return
    terminal = PromptToolkitTerminal()
