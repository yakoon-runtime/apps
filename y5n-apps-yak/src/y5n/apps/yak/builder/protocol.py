"""Builder protocol — language-agnostic interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArtifactInfo:
    name: str
    version: str
    host: str
    builder: str
    entry: str | None

    def __init__(
        self,
        name: str,
        version: str,
        host: str = "python",
        builder: str = "python",
        entry: str | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.host = host
        self.builder = builder
        self.entry = entry

    @property
    def filename(self) -> str:
        return f"{self.name}-{self.version}.{self.builder}.artifact"

    def to_yml(self) -> str:
        lines = [
            f"name: {self.name}",
            f"version: {self.version}",
            f"host: {self.host}",
            f"builder: {self.builder}",
        ]
        if self.entry:
            lines.append(f"entry: {self.entry}")
        return "\n".join(lines) + "\n"


class Builder(Protocol):
    def name(self) -> str: ...

    def detect(self, project_dir: Path) -> bool: ...

    def build(self, project_dir: Path, output_dir: Path) -> ArtifactInfo | None: ...
