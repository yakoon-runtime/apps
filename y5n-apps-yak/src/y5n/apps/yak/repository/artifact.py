from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from y5n.apps.yak.pack.models import PackName


@runtime_checkable
class ArtifactStore(Protocol):
    def get_artifact(self, name: PackName) -> Path | None: ...

    def has_artifact(self, name: PackName) -> bool: ...


class DirectoryArtifactStore:
    def __init__(self, *roots: Path) -> None:
        self._roots = list(roots)

    def get_artifact(self, name: PackName) -> Path | None:
        for root in self._roots:
            if root.name == name and root.is_dir():
                return root
            candidate = root / name
            if candidate.is_dir():
                return candidate
            candidate = root / f"y5n-packs-{name}"
            if candidate.is_dir():
                return candidate
            candidate = root / f"y5n-runtime-{name}"
            if candidate.is_dir():
                return candidate
        return None

    def has_artifact(self, name: PackName) -> bool:
        return self.get_artifact(name) is not None
