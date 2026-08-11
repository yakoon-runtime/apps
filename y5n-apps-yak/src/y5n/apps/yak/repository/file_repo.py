from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.pack.models import Mount, Pack, PackName, ToolReference


class FileRepository:
    def __init__(self, *roots: Path) -> None:
        self._roots = list(roots)

    def roots(self) -> list[Path]:
        return list(self._roots)

    def resolve_pack(self, name: str) -> Pack | None:
        """Resolve a pack's unit from its pack.toml."""
        resolved = self._resolve_pack(name)
        if resolved is not None:
            return resolved
        # Accept fully-qualified names ("y5n-packs-luma" → "luma").
        for prefix in ("y5n-packs-", "y5n-runtime-", "y5n-apps-", "y5n-sdk-"):
            if name.startswith(prefix):
                return self._resolve_pack(name[len(prefix) :])
        return None

    def resolve_pack_dir(self, name: str) -> Path | None:
        """Resolve a pack name to its source directory (with pack.toml)."""
        resolved = self._resolve_pack_dir(name)
        if resolved is not None:
            return resolved
        for prefix in ("y5n-packs-", "y5n-runtime-", "y5n-apps-", "y5n-sdk-"):
            if name.startswith(prefix):
                return self._resolve_pack_dir(name[len(prefix) :])
        return None

    def _resolve_pack_dir(self, name: str) -> Path | None:
        for root in self._roots:
            for prefix in ("y5n-packs-", "y5n-runtime-"):
                candidate = root / f"{prefix}{name}"
                if (candidate / "pack.toml").exists():
                    return candidate
        return None

    def _resolve_pack(self, name: str) -> Pack | None:
        dir_path = self._resolve_pack_dir(name)
        if dir_path is not None:
            return self._parse(dir_path / "pack.toml")
        return None

    def _parse(self, path: Path) -> Pack:
        import tomllib

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
