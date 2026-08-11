"""PythonBuildProvider — build Python wheels from pyproject.toml projects."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from y5n.apps.yak.builder.protocol import ArtifactInfo


class PythonBuildProvider:
    def name(self) -> str:
        return "python"

    def detect(self, project_dir: Path) -> bool:
        return (project_dir / "pyproject.toml").exists()

    def build(self, project_dir: Path, output_dir: Path) -> ArtifactInfo | None:
        if not self.detect(project_dir):
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", str(project_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

        wheels = list(project_dir.glob("dist/*.whl"))
        if not wheels:
            return None

        wheel = wheels[0]
        import hashlib

        wheel_bytes = wheel.read_bytes()
        fingerprint = hashlib.sha256(wheel_bytes).hexdigest()

        info = self._parse_wheel(wheel)
        if info is None:
            return None

        # A pack is identified by its pack.toml name, not its Python
        # distribution name ("system", not "y5n-packs-system").
        pack_manifest = project_dir / "pack.toml"
        if pack_manifest.exists():
            import tomllib

            with open(pack_manifest, "rb") as f:
                pack = tomllib.load(f)
            info.name = pack.get("name", info.name)
            info.version = pack.get("version", info.version)

        info.fingerprint = fingerprint

        artifact_dir = output_dir / info.filename
        artifact_dir.mkdir(parents=True, exist_ok=True)

        (artifact_dir / wheel.name).write_bytes(wheel_bytes)
        wheel.unlink()
        (artifact_dir / "artifact.yml").write_text(info.to_yml())
        return info

    def _parse_wheel(self, wheel: Path) -> ArtifactInfo | None:
        import zipfile

        try:
            with zipfile.ZipFile(wheel) as zf:
                names = [n for n in zf.namelist() if n.endswith("METADATA")]
                if not names:
                    return None
                meta = zf.read(names[0]).decode("utf-8")
        except Exception:
            return None

        name = ""
        version = ""
        for line in meta.splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()

        if not name or not version:
            return None

        return ArtifactInfo(name=name, version=version)
