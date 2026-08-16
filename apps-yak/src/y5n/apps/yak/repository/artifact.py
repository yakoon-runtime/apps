from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from y5n.apps.yak.cap.models import CapName


@runtime_checkable
class ArtifactStore(Protocol):
    def get_artifact(self, name: CapName) -> Path | None: ...

    def has_artifact(self, name: CapName) -> bool: ...


class DirectoryArtifactStore:
    def __init__(self, *roots: Path) -> None:
        self._roots = list(roots)

    def get_artifact(self, name: CapName) -> Path | None:
        """A root that is, or holds, the component's folder (folder == name).

        Identities are opaque: no family prefix is ever constructed from a
        name. ``cool-shell`` is looked up exactly as ``cool-shell``.
        """
        for root in self._roots:
            if root.name == name and root.is_dir():
                return root
            candidate = root / name
            if candidate.is_dir():
                return candidate
        return None

    def has_artifact(self, name: CapName) -> bool:
        return self.get_artifact(name) is not None
