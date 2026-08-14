"""Artifact models and resolution — language-neutral artifact handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from y5n.apps.yak.environment.models import Environment
from y5n.apps.yak.pack.models import PackName


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
        mount: str | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.kind = kind
        self.host = host
        self.builder = builder
        self.dependencies = dependencies or []
        self.fingerprint = fingerprint
        self.path = path
        self.mount = mount

    @property
    def package_file(self) -> Path | None:
        if self.path is None:
            return None
        for f in self.path.iterdir():
            if f.suffix == ".whl":
                return f
        return None

    @property
    def structure(self) -> Path | None:
        """The artifact's materializable tree (its pack structure)."""
        if self.path is None:
            return None
        structure = self.path / "structure"
        return structure if structure.is_dir() else None

    @property
    def manifest(self) -> Path | None:
        if self.path is None:
            return None
        return self.path / "artifact.yml"

    def is_meta(self) -> bool:
        return self.kind == "meta"


class ArtifactSource(Protocol):
    def resolve(self, name: str) -> Artifact | None: ...


def load_remote_environment(path: Path) -> Environment | None:
    """Parse an environment manifest (a plain YAML resource, not an artifact).

    The manifest declares the desired installation: a name and the
    components it materializes. It holds no infrastructure and no
    resolution logic — the resolver decides how each component is met.
    """
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None
    components = data.get("components", [])
    if not isinstance(components, list):
        return None
    return Environment(
        name=str(data.get("name", path.stem)),
        schema=str(data.get("schema", "1")),
        components=[PackName(c) for c in components],
    )


@runtime_checkable
class WritableRepository(Protocol):
    """A repository that can also receive artifacts (``deploy``)."""

    def deploy(self, name: str, artifact_dir: Path) -> bool: ...


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
                    mount=meta.get("mount"),
                )
        return None

    def list_artifacts(self) -> list[tuple[str, str]]:
        """List the artifacts in this root as (name, kind version)."""
        if not self._root.is_dir():
            return []
        found: list[tuple[str, str]] = []
        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir():
                continue
            manifest = entry / "artifact.yml"
            if not manifest.exists():
                continue
            meta = _parse_manifest(manifest)
            name = meta.get("name", "")
            if name:
                found.append(
                    (name, f"{meta.get('kind', 'package')} {meta.get('version', '?')}")
                )
        return found


def _parse_manifest(path: Path) -> dict:
    try:
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


@dataclass(frozen=True)
class WorkspaceManifest:
    """The ``workspace`` section of a meta artifact's manifest.

    ``path`` is relative to the environment root and says where the
    structure goes — ``structure`` for standalone environments,
    ``workspace/structure`` for the dev environment hosted in its source
    repo.
    """

    path: str = "structure"
    packs: list[str] = field(default_factory=list)
    mounts: list[dict] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


def load_workspace_manifest(path: Path) -> WorkspaceManifest | None:
    """Read a meta artifact's workspace manifest, or None when absent."""
    data = _parse_manifest(path)
    ws = data.get("workspace")
    if not isinstance(ws, dict):
        return None
    return WorkspaceManifest(
        path=ws.get("path", "structure"),
        packs=ws.get("packs", []) or [],
        mounts=ws.get("mounts", []) or [],
        dependencies=data.get("dependencies", []) or [],
    )
