from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from y5n.apps.yak.pack.models import PackName


class InstallationStatus(Enum):
    CREATED = "created"
    MATERIALIZED = "materialized"
    RUNNING = "running"
    STOPPED = "stopped"
    BROKEN = "broken"


@dataclass(frozen=True)
class Component:
    """An installed component — the IST record of one component.

    ``mode`` says how the component is made available:

    - ``source``: linked into the installation (dev loop); ``source`` is
      the symlink target (the pack's structure in a source tree).
    - ``artifact``: copied into the installation (self-contained);
      ``version`` + ``fingerprint`` identify the artifact.
    - ``tool``: a host app installed into the venv; no namespace.
    """

    name: str
    mode: str = "source"
    source: str = ""
    version: str = ""
    fingerprint: str = ""
    mount: str = ""
    package: str = ""


@dataclass
class Installation:
    name: str
    root: Path
    packs: list[PackName] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    status: InstallationStatus = InstallationStatus.CREATED
    created: datetime | None = None
    updated: datetime | None = None
