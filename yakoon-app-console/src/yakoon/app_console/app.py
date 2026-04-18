from yakoon.platform.transport import LocalTransport

from .runtime import ConsoleClient, create_runtime


async def run() -> None:

    # Startup
    host = await create_runtime()
    transport = LocalTransport(host)

    client = ConsoleClient(transport)
    await client.run()
