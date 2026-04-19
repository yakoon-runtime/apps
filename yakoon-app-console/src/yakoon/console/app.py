from yakoon.client.runtime import Client, create_runtime
from yakoon.client.terminal import PromptToolkitTerminal
from yakoon.platform.transport import LocalTransport

# from yakoon.transport_ws import WebSocketClientTransport
# from yakoon.client.terminal.simple import SimpleTerminal


async def run() -> None:

    # Startup
    host = await create_runtime()
    transport = LocalTransport(host)
    # transport2 = WebSocketClientTransport("ws://localhost:8000/ws")

    terminal = PromptToolkitTerminal()
    client = Client(transport)
    await client.run(terminal)
