from __future__ import annotations

from typing import TYPE_CHECKING

from y5n.base.config import load_config

if TYPE_CHECKING:
    from .app import TextualApp


def build_texture() -> TextualApp:
    from .app import TextualApp

    cfg, config_path = load_config()
    return TextualApp(config=cfg, config_path=config_path)
