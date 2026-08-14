from __future__ import annotations

import tomllib
from pathlib import Path

from y5n.apps.yak.pack.models import Mount, Pack, ToolReference


class FileRepository:
    def __init__(self, *roots: Path) -> None:
        self._roots = list(roots)

    def roots(self) -> list[Path]:
        return list(self._roots)

    def resolve_pack(self, name: str) -> Pack | None:
        """Resolve a pack from its pack.toml by its exact name.

        Folder equals name: a component lives in ``<root>/<name>`` with its
        own ``pack.toml``. The resolver knows no families and no prefixes —
        ``y5n-packs-system`` and ``my-super-pack`` resolve the same way,
        and a short name like ``system`` simply has no folder.
        """
        return self._resolve_pack(name)

    def resolve_pack_dir(self, name: str) -> Path | None:
        """Resolve a component name to its source directory (folder == name)."""
        return self._resolve_pack_dir(name)

    def _resolve_pack_dir(self, name: str) -> Path | None:
        """A source root that holds the component's folder (folder == name)."""
        for root in self._roots:
            candidate = root / name
            if (candidate / "pack.toml").exists():
                return candidate
        return None

    def _resolve_pack(self, name: str) -> Pack | None:
        dir_path = self._resolve_pack_dir(name)
        if dir_path is not None:
            return self._parse(dir_path / "pack.toml")
        return None

    def _parse(self, path: Path) -> Pack:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return Pack(
            name=data["name"],
            version=data.get("version", "0.1"),
            mount=data.get("mount"),
            mounts=[self._mount(m) for m in data.get("mounts", [])],
            tools=[self._tool(t) for t in data.get("tools", data.get("tool", []))],
        )

    @staticmethod
    def _tool(raw: dict | str) -> ToolReference:
        if isinstance(raw, str):
            return ToolReference(name=raw)
        return ToolReference(name=raw.get("name", ""))

    @staticmethod
    def _mount(raw: dict) -> Mount:
        return Mount(
            source=raw.get("source") or raw.get("pack", ""),
            target=raw.get("target", ""),
        )
