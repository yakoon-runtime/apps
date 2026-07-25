from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from y5n.apps.yak.distribution.models import PackName


class InstallationStatus(Enum):
    CREATED = "created"
    MATERIALIZED = "materialized"
    RUNNING = "running"
    STOPPED = "stopped"
    BROKEN = "broken"


@dataclass
class Installation:
    name: str
    distribution: str
    root: Path
    packs: list[PackName] = field(default_factory=list)
    status: InstallationStatus = InstallationStatus.CREATED
    created: datetime | None = None
    updated: datetime | None = None
