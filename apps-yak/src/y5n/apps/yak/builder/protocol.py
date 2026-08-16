"""Builder protocol — language-agnostic interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArtifactInfo:
    name: str
    version: str
    kind: str
    host: str
    builder: str
    entry: str | None
    fingerprint: str
    mount: str | None = None

    def __init__(
        self,
        name: str,
        version: str,
        kind: str = "package",
        host: str = "python",
        builder: str = "python",
        entry: str | None = None,
        fingerprint: str = "",
        mount: str | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.kind = kind
        self.host = host
        self.builder = builder
        self.entry = entry
        self.fingerprint = fingerprint
        self.mount = mount

    @property
    def filename(self) -> str:
        return f"{self.name}-{self.version}.{self.builder}.artifact"

    def to_yml(self) -> str:
        lines = [
            f"name: {self.name}",
            f"version: {self.version}",
            f"kind: {self.kind}",
            f"host: {self.host}",
            f"builder: {self.builder}",
        ]
        if self.mount:
            lines.append(f"mount: {self.mount}")
        if self.entry:
            lines.append(f"entry: {self.entry}")
        if self.fingerprint:
            lines.append(f"fingerprint: sha256:{self.fingerprint}")
        return "\n".join(lines) + "\n"


class Builder(Protocol):
    def name(self) -> str: ...

    def detect(self, project_dir: Path) -> bool: ...

    def build(self, project_dir: Path, output_dir: Path) -> ArtifactInfo | None: ...
