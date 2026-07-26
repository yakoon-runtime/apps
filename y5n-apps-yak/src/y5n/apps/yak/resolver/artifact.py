"""Artifact models and resolution — language-neutral artifact handling."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Artifact:
    """A resolved artifact — metadata + bytes on disk."""

    def __init__(
        self,
        name: str,
        version: str,
        kind: str = "package",
        host: str = "python",
        builder: str = "python",
        dependencies: list[str] | None = None,
        fingerprint: str = "",
        path: Path | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.kind = kind
        self.host = host
        self.builder = builder
        self.dependencies = dependencies or []
        self.fingerprint = fingerprint
        self.path = path

    @property
    def package_file(self) -> Path | None:
        if self.path is None:
            return None
        for f in self.path.iterdir():
            if f.suffix == ".whl":
                return f
        return None

    @property
    def manifest(self) -> Path | None:
        if self.path is None:
            return None
        return self.path / "artifact.yml"

    def is_meta(self) -> bool:
        return self.kind == "meta"


class ArtifactSource(Protocol):
    def resolve(self, name: str) -> Artifact | None: ...


class DirectorySource:
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
            if meta is not None and meta.get("name") == name:
                fp = meta.get("fingerprint", "")
                if fp.startswith("sha256:"):
                    fp = fp[7:]
                return Artifact(
                    name=meta["name"],
                    version=meta.get("version", "0"),
                    kind=meta.get("kind", "package"),
                    host=meta.get("host", "python"),
                    builder=meta.get("builder", "python"),
                    dependencies=meta.get("dependencies", []),
                    fingerprint=fp,
                    path=entry,
                )
        return None


def _parse_manifest(path: Path) -> dict:
    try:
        import yaml
        text = path.read_text()
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    try:
        meta: dict = {}
        deps: list[str] = []
        in_deps = False
        for line in path.read_text().splitlines():
            if in_deps:
                line = line.strip()
                if line.startswith("- "):
                    deps.append(line[2:])
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                if key.strip() == "dependencies":
                    in_deps = True
                else:
                    meta[key.strip()] = val.strip()
        if deps:
            meta["dependencies"] = deps
        return meta
    except Exception:
        return {}
