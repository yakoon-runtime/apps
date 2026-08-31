"""Artifact models and resolution — language-neutral artifact handling."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from y5n.apps.yak.resolver.distribution import version_key


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
        """The artifact's materializable tree (its mounted content).

        The mounted content is packaged into the artifact's canonical
        ``mount`` subdirectory (the component-side source name is a build
        concern — the relative source lives in the artifact's mount
        declaration).
        """
        if self.path is None:
            return None
        path = self.path / "mount"
        return path if path.is_dir() else None

    @property
    def manifest(self) -> Path | None:
        if self.path is None:
            return None
        return self.path / "artifact.yml"

    def is_meta(self) -> bool:
        return self.kind == "meta"


class ArtifactSource(Protocol):
    def resolve(self, name: str) -> Artifact | None: ...


@runtime_checkable
class WritableRepository(Protocol):
    """A repository that can also receive artifacts (``deploy``)."""

    def deploy(self, name: str, artifact_dir: Path) -> bool: ...


class DirectorySource:
    def __init__(self, root: Path) -> None:
        self._root = root

    def resolve(self, name: str) -> Artifact | None:
        """Resolve ``name`` to its newest artifact in this directory.

        The store may hold several versions of one artifact; the chosen
        one is the highest version, deterministically (version key, then
        directory name on ties) — never the first file the OS happens to
        list. Without an explicit version request, ``newest`` is the
        contract (mirrors the distribution's ``latest``).
        """
        if not self._root.is_dir():
            return None
        candidates: list[tuple[Path, dict]] = []
        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir():
                continue
            manifest = entry / "artifact.yml"
            if not manifest.exists():
                continue
            meta = _parse_manifest(manifest)
            if meta is not None and meta.get("name") == name:
                candidates.append((entry, meta))
        if not candidates:
            return None
        entry, meta = max(
            candidates,
            key=lambda item: (
                version_key(item[1].get("version", "0")),
                item[0].name,
            ),
        )
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
            mount=_mount_target(meta.get("mount")),
        )

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


def _mount_target(mount) -> str | None:
    """The tree target of an artifact.yml ``mount`` value.

    ``mount`` is a mapping ``{source, path}`` — the delivery declaration.
    """
    if isinstance(mount, dict):
        target = mount.get("path")
        return str(target) if target else None
    return None


def _parse_manifest(path: Path) -> dict:
    """Read an ``artifact.yml`` manifest (canonical YAML)."""
    try:
        text = path.read_text()
        data = yaml.safe_load(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
