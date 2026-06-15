"""Start a headless Runtime with WebSocket support.

Usage:

    python -m y5napp.runtime                    # port 9100
    python -m y5napp.runtime 9101               # custom port
    python -m y5napp.runtime 9100 "y5nspace.shell,y5nspace.os"
"""

import asyncio
import sys

from websockets.asyncio.server import serve
from y5n.runtime.settings import RuntimeSettings, Settings
from y5n.runtime.wire.runtime import build_runtime
from y5ntrans.websocket.server import WebSocketServerTransport

HOST = "127.0.0.1"
_host = None


def default_spaces():
    return [
        "y5nspace.runtime",
        "y5nspace.shell",
        "y5nspace.ident",
        "y5nspace.os",
    ]


async def handler(websocket):
    transport = WebSocketServerTransport(_host)
    _, recv = await transport.connect(websocket)
    await recv()


def main(args: list[str] | None = None) -> None:
    args = args or sys.argv[1:]
    port = int(args[0]) if args else 9100
    spaces = args[1].split(",") if len(args) > 1 else default_spaces()

    settings = Settings(
        runtime=RuntimeSettings(
            known={
                "office": "ws://localhost:9100",
                "server": "ws://localhost:9101",
                "production": "ws://localhost:9102",
            }
        )
    )
    settings.runtime.spaces = spaces

    async def _run():
        global _host
        runtime = build_runtime(capabilities={}, settings=settings)
        _host = runtime
        await _host.setup()
        print("Yakoon Runtime", flush=True)
        print(flush=True)
        print(f"Listen : ws://{HOST}:{port}", flush=True)
        print(f"Spaces : {', '.join(spaces)}", flush=True)
        print(flush=True)
        print("Ready.", flush=True)
        async with serve(handler, HOST, port):
            await asyncio.get_running_loop().create_future()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
