from __future__ import annotations

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from importlib.resources import files

from y5n.base.theme import ThemeManager, default_themes

from .conf import WebConfig

THEMES = default_themes()
STATIC = files("y5napp.web").joinpath("static")


def _inject_config(html: str, cfg: WebConfig, runtime_url: str) -> str:
    script = f"<script>window.__YAKOON_RUNTIMES = [{{url: {json.dumps(runtime_url)}, autoconnect: true}}]</script>"
    return html.replace("</head>", f"{script}\n</head>")


def _inject_theme(html: str, cfg: WebConfig) -> str:
    if not cfg.theme:
        return html
    mgr = ThemeManager(THEMES)
    css = mgr.as_css_vars(cfg.theme)
    if not css:
        return html
    style = f"<style>\n{css}\n</style>"
    return html.replace("</head>", f"{style}\n</head>")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, config: WebConfig, runtime_url: str, **kwargs):
        self._config = config
        self._runtime_url = runtime_url
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def _serve_html(self, path: str) -> None:
        with open(path, "rb") as f:
            raw = f.read()
        html = raw.decode("utf-8")
        html = _inject_config(html, self._config, self._runtime_url)
        html = _inject_theme(html, self._config)
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


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    runtime_url: str = "ws://localhost:9100",
    config: WebConfig | None = None,
) -> HTTPServer:
    class ConfigHandler(Handler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, config=config or WebConfig(), runtime_url=runtime_url, **kwargs)

    server = HTTPServer((host, port), ConfigHandler)
    print("Yakoon Web", flush=True)
    print(flush=True)
    print(f"URL     : http://{host}:{port}", flush=True)
    print(f"Runtime : {runtime_url}", flush=True)
    return server
