"""Artifact models and resolution — language-neutral artifact handling."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Artifact:
    """A resolved artifact — metadata + bytes on disk."""

    name: str
    version: str
    host: str
    builder: str
    path: Path  # the .artifact directory

    def __init__(
        self,
        name: str,
        version: str,
        host: str,
        builder: str,
        path: Path,
    ) -> None:
        self.name = name
        self.version = version
        self.host = host
        self.builder = builder
        self.path = path

    @property
    def package_file(self) -> Path | None:
        for f in self.path.iterdir():
            if f.suffix == ".whl":
                return f
        return None

    @property
    def manifest(self) -> Path:
        return self.path / "artifact.yml"


class ArtifactSource(Protocol):
    """A source that stores and serves artifacts."""

    def resolve(self, name: str) -> Artifact | None: ...


class DirectorySource:
    """Resolves artifacts from a local directory of .artifact folders."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def resolve(self, name: str) -> Artifact | None:
        if not self._root.is_dir():
            return None
        for entry in self._root.iterdir():
            if not entry.is_dir():
                continue
            manifest = entry / "artifact.yml"
            if not manifest.exists():
                continue
            meta = _parse_manifest(manifest)
            if meta is not None and meta["name"] == name:
                return Artifact(
                    name=meta["name"],
                    version=meta.get("version", "0"),
                    host=meta.get("host", "python"),
                    builder=meta.get("builder", "python"),
                    path=entry,
                )
        return None


def _parse_manifest(path: Path) -> dict[str, str] | None:
    try:
        text = path.read_text()
        meta: dict[str, str] = {}
        for line in text.strip().splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip()
        return meta
    except Exception:
        return None
