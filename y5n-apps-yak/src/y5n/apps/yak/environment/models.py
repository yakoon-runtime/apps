from __future__ import annotations

from dataclasses import dataclass, field

from y5n.apps.yak.distribution.models import Mount, PackName


@dataclass
class Environment:
    name: str
    schema: str = "1"
    dependencies: list[PackName] = field(default_factory=list)
    mounts: list[Mount] = field(default_factory=list)
    workspace_path: str = "structure"
