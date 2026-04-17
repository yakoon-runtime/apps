from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
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
    runtime = await create_runtime()
    transport = WebSocketTransport(runtime)

    app.state.runtime = runtime
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
WEB_DIR = PROJECT_ROOT / "clients" / "web"

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


def get_transport(app: FastAPI) -> WebSocketTransport:
    return app.state.transport
