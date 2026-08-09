from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml
from y5n.runtime.store.event.settings import Backend

CONFIG_FILENAME = "yakoon-runtime.yml"


@dataclass
class ListenConfig:
    host: str = "127.0.0.1"
    port: int = 9100


@dataclass
class StoreConfig:
    backend: Backend = "memory"
    dsn: str = ""


@dataclass
class RuntimeConfig:
    name: str = ""
    listen: ListenConfig = field(default_factory=ListenConfig)
    known: dict[str, str] = field(default_factory=dict)
    workspace_path: str = ""
    stores: dict[str, StoreConfig] = field(default_factory=dict)


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
    stores_raw = data.get("stores")
    stores = {
        name: StoreConfig(**cfg)
        for name, cfg in (stores_raw or {}).items()
        if isinstance(cfg, dict)
    }
    return RuntimeConfig(
        name=data.get("name", ""),
        listen=(
            ListenConfig(**listen_raw)
            if isinstance(listen_raw, dict)
            else ListenConfig()
        ),
        known=data.get("known", {}),
        workspace_path=data.get("workspace_path", ""),
        stores=stores,
    )


def load_config() -> RuntimeConfig:

    for p in _search_paths():
        if p.exists():
            with open(p) as f:
                return _from_dict(yaml.safe_load(f) or {})

    try:
        bundled = files("y5n.apps.runtime").joinpath("yakoon-runtime.yml")
        with bundled.open("r") as f:
            return _from_dict(yaml.safe_load(f) or {})
    except FileNotFoundError:
        pass

    return RuntimeConfig()
