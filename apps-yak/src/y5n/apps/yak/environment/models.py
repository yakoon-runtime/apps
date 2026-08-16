from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from y5n.apps.yak.cap.models import Mount


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

    def workspace_dir(self, context_root: Path) -> Path:
        """The materialization target, relative to the Yak state root.

        ``workspace_path`` names the workspace inside ``<context_root>/.yak/``
        — the default ``structure`` resolves to ``<context_root>/.yak/structure``.
        Mounts are interpreted relative to this directory; ``/`` is its root.
        """
        return context_root / ".yak" / self.workspace_path
