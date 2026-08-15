from __future__ import annotations

from dataclasses import dataclass, field
from typing import NewType

PackName = NewType("PackName", str)


@dataclass(frozen=True)
class ToolReference:
    name: str


@dataclass(frozen=True)
class Mount:
    source: str
    target: str


@dataclass(frozen=True)
class Pack:
    """A resolved pack unit — what ``yak install`` composes from a pack.toml.

    ``mount`` is the tree path the pack's structure is mounted into
    (e.g. ``/usr/bin`` for the system pack). ``mounts`` declare other
    structures this pack's tree includes; ``tools`` name host apps the
    pack needs.
    """

    name: str
    version: str
    mount: str | None = None
    mounts: list[Mount] = field(default_factory=list)
    tools: list[ToolReference] = field(default_factory=list)
