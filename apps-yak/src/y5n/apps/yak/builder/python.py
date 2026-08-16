"""PythonBuildProvider — build Python wheels from pyproject.toml projects."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from y5n.apps.yak.builder.protocol import ArtifactInfo
from y5n.apps.yak.cap.models import read_mount


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
        wheel_bytes = wheel.read_bytes()
        fingerprint = hashlib.sha256(wheel_bytes).hexdigest()

        info = self._parse_wheel(wheel)
        if info is None:
            return None

        # The artifact's identity is the builder's result — the wheel's
        # own name and version from pyproject.toml. No other manifest may
        # relabel it afterwards.
        info.mount = read_mount(project_dir)

        artifact_dir = output_dir / info.filename
        artifact_dir.mkdir(parents=True, exist_ok=True)

        if info.mount:
            structure = project_dir / "structure"
            if structure.is_dir():
                shutil.copytree(
                    structure, artifact_dir / "structure", dirs_exist_ok=True
                )

        info.fingerprint = fingerprint

        (artifact_dir / wheel.name).write_bytes(wheel_bytes)
        wheel.unlink()
        (artifact_dir / "artifact.yml").write_text(info.to_yml())
        return info

    def _parse_wheel(self, wheel: Path) -> ArtifactInfo | None:
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
