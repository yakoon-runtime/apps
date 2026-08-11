from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.distribution.models import (
    Distribution,
    Mount,
    PackName,
    PackReference,
    ToolReference,
    VersionConstraint,
)


class FileRepository:
    def __init__(self, *roots: Path) -> None:
        self._roots = list(roots)

    def roots(self) -> list[Path]:
        return list(self._roots)

    def resolve_distribution(self, name: str) -> Distribution | None:
        """Resolve a pack's distribution from its pack.toml."""
        resolved = self._resolve_pack(name)
        if resolved is not None:
            return resolved
        # Accept fully-qualified names ("y5n-packs-luma" → "luma").
        for prefix in ("y5n-packs-", "y5n-runtime-", "y5n-apps-", "y5n-sdk-"):
            if name.startswith(prefix):
                return self._resolve_pack(name[len(prefix) :])
        return None

    def _resolve_pack(self, name: str) -> Distribution | None:
        for root in self._roots:
            for prefix in ("y5n-packs-", "y5n-runtime-"):
                dist_path = root / f"{prefix}{name}" / "pack.toml"
                if dist_path.exists():
                    return self._parse(dist_path)
        return None

    def resolve_pack(self, name: PackName) -> bool:
        for root in self._roots:
            if self._find_manifest(root, name):
                return True
        return False

    def _find_manifest(self, root: Path, name: PackName) -> Path | None:
        for candidate in (
            root / name,
            root / f"y5n-packs-{name}",
            root / f"y5n-runtime-{name}",
        ):
            manifest = candidate / "pack.toml"
            if manifest.exists():
                return manifest
        return None

    def _parse(self, path: Path) -> Distribution:
        import tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)
        return Distribution(
            name=data["name"],
            version=data.get("version", "0.1"),
            distributions=[
                self._pack_ref(p)
                for p in data.get("distributions", data.get("distribution", []))
            ],
            mounts=[self._mount(m) for m in data.get("mounts", data.get("mount", []))],
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

    @staticmethod
    def _pack_ref(raw: str | dict) -> PackReference:
        if isinstance(raw, str):
            return PackReference(name=PackName(raw))
        name = raw.get("name", "")
        version = raw.get("version")
        return PackReference(
            name=PackName(name),
            version=VersionConstraint(version) if version else None,
        )
