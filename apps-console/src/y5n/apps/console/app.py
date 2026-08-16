from y5n.apps.console.runtime import Client, create_runtime
from y5n.apps.console.terminal import SimpleTerminal
from y5n.runtime.engine.transport import LocalTransport


async def run() -> None:

    host = await create_runtime()
    await host.setup()

    transport = LocalTransport(host)

    client = Client(transport)
    await client.run(SimpleTerminal())
