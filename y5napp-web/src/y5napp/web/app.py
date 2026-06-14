from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ------------------------
# App
# ------------------------

app = FastAPI()

# ------------------------
# Static UI
# ------------------------

WEB_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "clients" / "y5ncli-web"

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
