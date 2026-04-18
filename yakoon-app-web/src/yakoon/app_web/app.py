from __future__ import annotations

import importlib.resources as pkg
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from yakoon.transport_ws import WebSocketTransport

from .adapter import FastAPIWebSocketAdapter
from .runtime import create_runtime, find_project_root

# ------------------------
# Lifespan
# ------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Startup
    host = await create_runtime()
    transport = WebSocketTransport(host)

    app.state.runtime = host
    app.state.transport = transport

    yield

    # Shutdown (optional später)
    # await runtime.shutdown()


# ------------------------
# App
# ------------------------

app = FastAPI(lifespan=lifespan)


# ------------------------
# Static UI
# ------------------------

BASE_DIR = Path(__file__).resolve()

PROJECT_ROOT = find_project_root(BASE_DIR)
WEB_DIR = PROJECT_ROOT / "clients" / "yakoon-client-web"

app.mount(
    "/js",
    StaticFiles(directory=WEB_DIR / "js"),
    name="js",
)
app.mount(
    "/assets",
    StaticFiles(directory=WEB_DIR / "assets"),
    name="assets",
)


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


# ------------------------
# WebSocket Endpoint
# ------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):

    await ws.accept()

    adapter = FastAPIWebSocketAdapter(ws)

    transport = get_transport(app)
    connection, receive_loop = await transport.connect(adapter)

    await receive_loop()


# ------------------------
# HTTP RESSOURCES
# ------------------------


@app.get("/api/assets/{package}/{path:path}")
def get_asset(package: str, path: str):

    # Security
    if ".." in path:
        raise HTTPException(400)

    try:
        base = pkg.files(package)
        resource = base.joinpath(path)

        if not resource.is_file():
            raise HTTPException(404)

        # Content-Type korrekt bestimmen
        content_type, _ = mimetypes.guess_type(str(resource))
        if not content_type:
            content_type = "application/octet-stream"

        return StreamingResponse(
            resource.open("rb"),
            media_type=content_type,
        )

    except Exception:
        raise HTTPException(404) from Exception


def get_transport(app: FastAPI) -> WebSocketTransport:
    return app.state.transport
