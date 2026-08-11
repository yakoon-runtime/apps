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
    """A resolved pack unit — what ``yak add`` installs from a pack.toml.

    ``mounts`` declare other structures this pack's tree includes; the
    mount sources are the packs it depends on. ``tools`` name host apps
    the pack needs.
    """

    name: str
    version: str
    mounts: list[Mount] = field(default_factory=list)
    tools: list[ToolReference] = field(default_factory=list)
