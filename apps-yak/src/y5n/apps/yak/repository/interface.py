from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from y5n.apps.yak.cap.models import Cap


@runtime_checkable
class Repository(Protocol):
    def resolve_pack(self, name: str) -> Cap | None: ...

    def resolve_pack_dir(self, name: str) -> Path | None: ...

    def roots(self) -> list[Path]: ...
