from __future__ import annotations

from dataclasses import dataclass, field
from typing import NewType

PackName = NewType("PackName", str)


@dataclass(frozen=True)
class ToolReference:
    name: str


@dataclass(frozen=True)
class VersionConstraint:
    specifier: str


@dataclass(frozen=True)
class PackReference:
    name: PackName
    version: VersionConstraint | None = None


@dataclass(frozen=True)
class Mount:
    source: str
    target: str


@dataclass(frozen=True)
class Distribution:
    name: str
    version: str
    development: bool = False
    mounts: list[Mount] = field(default_factory=list)
    distributions: list[PackReference] = field(default_factory=list)
    packs: list[PackName] = field(default_factory=list)
    tools: list[ToolReference] = field(default_factory=list)
