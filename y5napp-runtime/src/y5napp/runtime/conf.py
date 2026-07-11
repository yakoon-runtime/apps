from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

CONFIG_FILENAME = "yakoon-runtime.yml"


@dataclass
class ListenConfig:
    host: str = "127.0.0.1"
    port: int = 9100


@dataclass
class RuntimeConfig:
    name: str = ""
    listen: ListenConfig = field(default_factory=ListenConfig)
    known: dict[str, str] = field(default_factory=dict)
    root_path: str = ""


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


def _from_dict(data: dict) -> RuntimeConfig:
    listen_raw = data.get("listen")
    return RuntimeConfig(
        name=data.get("name", ""),
        listen=ListenConfig(**listen_raw) if isinstance(listen_raw, dict) else ListenConfig(),
        known=data.get("known", {}),
        root_path=data.get("root_path", ""),
    )


def load_config() -> RuntimeConfig:
    for p in _search_paths():
        if p.exists():
            with open(p) as f:
                return _from_dict(yaml.safe_load(f) or {})

    bundled = files("y5napp.runtime").joinpath("yakoon-runtime.yml")
    if bundled.exists():
        with open(bundled) as f:
            return _from_dict(yaml.safe_load(f) or {})

    return RuntimeConfig()
