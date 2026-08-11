from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from y5n.apps.yak.distribution.models import Distribution, PackName


@runtime_checkable
class Repository(Protocol):
    def resolve_distribution(self, name: str) -> Distribution | None: ...

    def resolve_pack(self, name: PackName) -> bool: ...

    def roots(self) -> list[Path]: ...

    def builtin_artifacts_dir(self) -> Path | None: ...
