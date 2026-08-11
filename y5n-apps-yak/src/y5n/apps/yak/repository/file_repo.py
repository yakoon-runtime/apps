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
    def __init__(self, *roots: Path, builtin_artifacts: Path | None = None) -> None:
        self._roots = list(roots)
        self._artifacts_dir = builtin_artifacts

    def roots(self) -> list[Path]:
        return list(self._roots)

    def builtin_artifacts_dir(self) -> Path | None:
        """The bundled artifacts directory (meta distributions), if any."""
        return self._artifacts_dir

    def resolve_distribution(self, name: str) -> Distribution | None:
        resolved = self._resolve_distribution(name)
        if resolved is not None:
            return resolved
        # Accept fully-qualified names ("y5n-packs-luma" → "luma").
        for prefix in ("y5n-packs-", "y5n-runtime-", "y5n-apps-", "y5n-sdk-"):
            if name.startswith(prefix):
                return self._resolve_distribution(name[len(prefix) :])
        return None

    def _resolve_distribution(self, name: str) -> Distribution | None:
        # 1. Bundled artifacts (apps/y5n-apps-yak/artifacts/<name>.yml)
        if self._artifacts_dir is not None:
            yml = self._artifacts_dir / f"{name}.yml"
            if yml.exists():
                return self._parse_artifact_yml(yml)

        # 2. Pack manifests across all roots
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

    def _parse_artifact_yml(self, path: Path) -> Distribution | None:
        import yaml

        try:
            data = yaml.safe_load(path.read_text())
        except Exception:
            return None
        if not isinstance(data, dict):
            return None

        name = data.get("name", "")
        development = data.get("kind") == "development"

        # Resolve extends
        extends = data.get("extends")
        if extends:
            parent = self._resolve_extends(extends)
            if parent is None:
                return None
            mounts = [
                self._mount(m) for m in data.get("workspace", {}).get("mounts", [])
            ]
            parent_mounts = [
                m for m in parent.mounts if m.source not in {mo.source for mo in mounts}
            ]
            all_mounts = parent_mounts + mounts

            tools = [self._tool(t) for t in data.get("tools", [])]
            parent_tools = parent.tools
            all_tools = parent_tools + tools

            return Distribution(
                name=name,
                version=data.get("version", "0.1"),
                development=development,
                mounts=all_mounts,
                tools=all_tools,
            )

        mounts = [self._mount(m) for m in data.get("workspace", {}).get("mounts", [])]
        tools = [self._tool(t) for t in data.get("tools", [])]
        return Distribution(
            name=name,
            version=data.get("version", "0.1"),
            development=development,
            mounts=mounts,
            tools=tools,
        )

    def _resolve_extends(self, name: str) -> Distribution | None:
        return self.resolve_distribution(name)

    @staticmethod
    def _tool(raw: dict | str) -> ToolReference:
        if isinstance(raw, str):
            ot = ToolReference(name=raw)
            return ot
        return ToolReference(
            name=raw.get("name", ""), optional=raw.get("optional", False)
        )

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
