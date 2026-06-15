from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

CONFIG_FILENAME = "yakoon-texture.yml"


@dataclass
class RuntimeEntry:
    name: str
    url: str
    autoconnect: bool = True


@dataclass
class TextureConfig:
    theme: str | None = None
    runtimes: list[RuntimeEntry] = field(default_factory=list)


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


def _from_dict(data: dict) -> TextureConfig:
    runtimes = [
        RuntimeEntry(
            name=r.get("name", r["url"]),
            url=r["url"],
            autoconnect=r.get("autoconnect", True),
        )
        for r in data.get("runtimes", [])
    ]
    return TextureConfig(
        theme=data.get("theme"),
        runtimes=runtimes,
    )


def load_config() -> tuple[TextureConfig, Path | None]:
    for p in _search_paths():
        if p.exists():
            with open(p) as f:
                return _from_dict(yaml.safe_load(f) or {}), p

    bundled = files("y5napp.textual").joinpath("yakoon-texture.yml")
    if bundled.exists():
        with open(bundled) as f:
            return _from_dict(yaml.safe_load(f) or {}), bundled

    return TextureConfig(), None
