from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.pack.models import Pack, read_mount


class FileRepository:
    def __init__(self, *roots: Path) -> None:
        self._roots = list(roots)

    def roots(self) -> list[Path]:
        return list(self._roots)

    def resolve_pack(self, name: str) -> Pack | None:
        """Resolve a source component from its native project manifest.

        Folder equals name: a component lives in ``<root>/<name>`` and is
        recognized by its pyproject.toml. The resolver knows no families
        and no prefixes — ``y5n-packs-system`` and ``my-super-pack``
        resolve the same way.
        """
        return self._resolve_pack(name)

    def resolve_pack_dir(self, name: str) -> Path | None:
        """Resolve a component name to its source directory (folder == name)."""
        return self._resolve_pack_dir(name)

    def _resolve_pack_dir(self, name: str) -> Path | None:
        """A source root that holds the component's folder (folder == name)."""
        for root in self._roots:
            candidate = root / name
            if (candidate / "pyproject.toml").exists():
                return candidate
        return None

    def _resolve_pack(self, name: str) -> Pack | None:
        dir_path = self._resolve_pack_dir(name)
        if dir_path is not None:
            return self._parse(dir_path)
        return None

    def _parse(self, project_dir: Path) -> Pack:
        return Pack(name=project_dir.name, mount=read_mount(project_dir))
