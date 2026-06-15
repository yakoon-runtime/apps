from __future__ import annotations

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from importlib.resources import files

from y5n.base.config import load_config
from y5n.base.theme import ThemeManager, default_themes

THEMES = default_themes()
STATIC = files("y5napp.web").joinpath("static")


def _inject_config(html: str) -> str:
    cfg, _ = load_config()
    runtimes = []
    for rt in cfg.runtimes or []:
        runtimes.append({
            "name": rt.name,
            "url": rt.url,
            "autoconnect": rt.autoconnect,
        })
    script = f"<script>window.__YAKOON_RUNTIMES = {json.dumps(runtimes)}</script>"
    return html.replace("</head>", f"{script}\n</head>")


def _inject_theme(html: str) -> str:
    cfg, _ = load_config()
    if not cfg.theme:
        return html
    mgr = ThemeManager(THEMES)
    css = mgr.as_css_vars(cfg.theme)
    if not css:
        return html
    style = f"<style>\n{css}\n</style>"
    return html.replace("</head>", f"{style}\n</head>")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def _serve_html(self, path: str) -> None:
        with open(path, "rb") as f:
            raw = f.read()
        html = raw.decode("utf-8")
        html = _inject_config(html)
        html = _inject_theme(html)
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if os.path.isfile(path) and path.endswith(".html"):
            self._serve_html(path)
            return
        super().do_GET()


def serve(host: str = "127.0.0.1", port: int = 8000) -> HTTPServer:
    server = HTTPServer((host, port), Handler)
    print("Yakoon Web", flush=True)
    print(flush=True)
    print(f"URL     : http://{host}:{port}", flush=True)
    print(f"Runtime : ws://localhost:9100", flush=True)
    print(flush=True)
    print("Ready.", flush=True)
    return server
