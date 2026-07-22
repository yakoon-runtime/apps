"""Start a headless Runtime with WebSocket support.

Usage:

    python -m y5napp.runtime                    # port from config
    python -m y5napp.runtime 9101               # override port
"""

import asyncio
import sys

from websockets.asyncio.server import serve
from y5n.runtime.engine.settings import RuntimeSettings, Settings
from y5n.runtime.engine.wire.runtime import build_runtime
from y5ntrans.websocket.server import WebSocketServerTransport

from .conf import load_config

_host = None


async def handler(websocket):
    transport = WebSocketServerTransport(_host)
    _, recv = await transport.connect(websocket)
    await recv()


def main(args: list[str] | None = None) -> None:
    args = args or sys.argv[1:]

    cfg = load_config()
    host = cfg.listen.host
    port = int(args[0]) if args else cfg.listen.port

    settings = Settings(
        runtime=RuntimeSettings(
            known=cfg.known,
            workspace_path=cfg.workspace_path,
        )
    )

    async def _run():
        global _host
        runtime = build_runtime(settings=settings)
        _host = runtime
        await _host.setup()
        print("Yakoon Runtime", flush=True)
        print(flush=True)
        print(f"Listen : ws://{host}:{port}", flush=True)
        print(flush=True)
        print("Ready.", flush=True)
        try:
            async with serve(handler, host, port):
                await asyncio.get_running_loop().create_future()
        finally:
            print(flush=True)
            print("Stopping runtime...", flush=True)
            print("Done.", flush=True)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
