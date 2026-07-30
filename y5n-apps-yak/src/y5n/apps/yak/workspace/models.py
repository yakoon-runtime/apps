from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Workspace:
    path: Path
    distribution: str
    created: datetime | None = None
    updated: datetime | None = None
