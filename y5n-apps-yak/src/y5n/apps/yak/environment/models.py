from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from y5n.apps.yak.pack.models import Mount


@dataclass
class Environment:
    """The environment's declaration (SOLL) — what the user asked for.

    ``install`` maps each install identity (a bundle name) to the
    ``--path`` catalogs that override source resolution for it. Component
    membership, modes and fingerprints are resolution results and live in
    ``state.toml`` (IST), never here.
    """

    name: str
    schema: str = "2"
    install: dict[str, list[str]] = field(default_factory=dict)
    mounts: list[Mount] = field(default_factory=list)
    workspace_path: str = "structure"
    created: datetime | None = None
    updated: datetime | None = None
