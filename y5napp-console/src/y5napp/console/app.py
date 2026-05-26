from y5n.runtime.transport import LocalTransport
from y5ncli.console.client.runtime import Client, create_runtime
from y5ncli.console.client.terminal import PromptToolkitTerminal

# from y5n.transport_ws import WebSocketClientTransport
# from y5n.client.terminal.simple import SimpleTerminal


async def run() -> None:

    # Startup
    host = await create_runtime()
    await host.setup()

    transport = LocalTransport(host)
    # transport2 = WebSocketClientTransport("ws://localhost:8000/ws")

    terminal = PromptToolkitTerminal()
    client = Client(transport)

    await client.run(terminal)
