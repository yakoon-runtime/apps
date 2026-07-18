from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

CONFIG_FILENAME = "yakoon-web.yml"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass
class RuntimeConfig:
    url: str = "ws://localhost:9100"


@dataclass
class WebConfig:
    theme: str | None = None
    server: ServerConfig = field(default_factory=ServerConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def _search_paths() -> list[Path]:
    cwd = Path.cwd()
    paths: list[Path] = []
    for parent in [cwd, *cwd.parents]:
        p = parent / CONFIG_FILENAME
        paths.append(p)
        if p.exists():
            break
    paths.append(Path.home() / ".config" / "y5n" / CONFIG_FILENAME)
    return paths


def _from_dict(data: dict) -> WebConfig:
    server_raw = data.get("server")
    runtime_raw = data.get("runtime")
    return WebConfig(
        theme=data.get("theme"),
        server=(
            ServerConfig(**server_raw)
            if isinstance(server_raw, dict)
            else ServerConfig()
        ),
        runtime=(
            RuntimeConfig(**runtime_raw)
            if isinstance(runtime_raw, dict)
            else RuntimeConfig()
        ),
    )


def load_config() -> WebConfig:
    for p in _search_paths():
        if p.exists():
            with open(p) as f:
                return _from_dict(yaml.safe_load(f) or {})

    bundled = files("y5napp.web").joinpath("yakoon-web.yml")
    if bundled.exists():
        with open(bundled) as f:
            return _from_dict(yaml.safe_load(f) or {})

    return WebConfig()
