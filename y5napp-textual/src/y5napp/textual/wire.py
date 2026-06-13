from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .app import RuntimeConfig

if TYPE_CHECKING:
    from .app import TextualApp


def _config_paths() -> list[Path]:
    return [
        Path.cwd() / "texture.yaml",
        Path("~/.config/y5n/texture.yaml").expanduser(),
    ]


def _load_config() -> list[RuntimeConfig]:
    for p in _config_paths():
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f)
            if not data or "runtimes" not in data:
                return []
            return [
                RuntimeConfig(
                    name=r.get("name", r["url"]),
                    url=r["url"],
                    autoconnect=r.get("autoconnect", True),
                )
                for r in data["runtimes"]
            ]
    return []


def build_texture() -> TextualApp:
    from .app import TextualApp

    configs = _load_config()
    return TextualApp(configs=configs)
