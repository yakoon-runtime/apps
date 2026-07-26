"""Start a headless Runtime with WebSocket support.

Usage:

    python -m y5n.apps.runtime                    # port from config
    python -m y5n.apps.runtime 9101               # override port

The runtime resolves its workspace from the project context (yak.yml → env.yml).
"""

import asyncio
import sys
from pathlib import Path

from websockets.asyncio.server import serve
from y5n.runtime.engine.settings import RuntimeSettings, Settings
from y5n.runtime.engine.wire.runtime import build_runtime
from y5n.runtime.transport.server import WebSocketServerTransport

from .conf import load_config

_host = None


def _resolve_workspace() -> str:
    """Read workspace path from .yak/environment.yml, walking up from CWD."""
    import yaml

    cwd = Path.cwd()

    for parent in [cwd, *cwd.parents]:
        env_yml = parent / ".yak" / "environment.yml"
        if env_yml.exists():
            try:
                data = yaml.safe_load(env_yml.read_text())
                ws = data.get("workspace", {})
                path = (
                    ws.get("path", "structure") if isinstance(ws, dict) else "structure"
                )
                return str(parent / path)
            except Exception:
                pass

    # Fallback: monorepo boot path
    return "structure"


async def handler(websocket):
    transport = WebSocketServerTransport(_host)
    _, recv = await transport.connect(websocket)
    await recv()


def main(args: list[str] | None = None) -> None:
    args = args or sys.argv[1:]

    cfg = load_config()
    host = cfg.listen.host
    port = int(args[0]) if args else cfg.listen.port

    workspace_path = _resolve_workspace()

    settings = Settings(
        runtime=RuntimeSettings(
            known=cfg.known,
            workspace_path=workspace_path,
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
