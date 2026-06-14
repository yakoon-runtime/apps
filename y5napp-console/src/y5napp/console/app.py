from y5n.runtime.transport import LocalTransport
from y5napp.console.client.runtime import Client, create_runtime
from y5napp.console.client.terminal import SimpleTerminal


async def run() -> None:

    host = await create_runtime()
    await host.setup()

    transport = LocalTransport(host)

    client = Client(transport)
    await client.run(SimpleTerminal())
