"""Start a headless Runtime with WebSocket support.

Usage:

    python -m y5napp.runtime                    # port 9100
    python -m y5napp.runtime 9101               # custom port
"""

import asyncio
import sys
from importlib.resources import files
from urllib.parse import urlparse

import yaml
from websockets.asyncio.server import serve
from y5n.base.config import RuntimeFileConfig, load_runtime_config
from y5n.runtime.settings import RuntimeSettings, Settings
from y5n.runtime.wire.runtime import build_runtime
from y5ntrans.websocket.server import WebSocketServerTransport

_host = None


def _load_config() -> RuntimeFileConfig:
    cfg, path = load_runtime_config()
    if path:
        return cfg

    bundled = files("y5napp.runtime").joinpath("yakoon-runtime.yml")
    if bundled.exists():
        with open(bundled) as f:
            data = yaml.safe_load(f) or {}
        return RuntimeFileConfig(
            listen=data.get("listen", "ws://127.0.0.1:9100"),
            spaces=data.get("spaces", []),
            known=data.get("known", {}),
        )

    return RuntimeFileConfig()


async def handler(websocket):
    transport = WebSocketServerTransport(_host)
    _, recv = await transport.connect(websocket)
    await recv()


def main(args: list[str] | None = None) -> None:
    args = args or sys.argv[1:]

    cfg = _load_config()
    parsed = urlparse(cfg.listen)
    host = parsed.hostname or "127.0.0.1"
    port = int(args[0]) if args else (parsed.port or 9100)

    settings = Settings(
        runtime=RuntimeSettings(
            known=cfg.known,
        )
    )
    settings.runtime.spaces = cfg.spaces

    async def _run():
        global _host
        runtime = build_runtime(capabilities={}, settings=settings)
        _host = runtime
        await _host.setup()
        print("Yakoon Runtime", flush=True)
        print(flush=True)
        print(f"Listen : ws://{host}:{port}", flush=True)
        if cfg.spaces:
            print(f"Spaces : {', '.join(s.rsplit('.', 1)[-1] for s in cfg.spaces)}", flush=True)
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
