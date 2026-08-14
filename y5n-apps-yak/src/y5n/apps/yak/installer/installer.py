from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

from y5n.apps.yak.installation.models import Installation
from y5n.apps.yak.installer.venv import ensure_venv, upgrade_pip
from y5n.apps.yak.repository.artifact import ArtifactStore


def _has_project_file(directory: Path) -> bool:
    return (
        (directory / "pyproject.toml").exists()
        or (directory / "setup.py").exists()
        or (directory / "setup.cfg").exists()
    )


class Installer:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        runtime_root: Path | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._runtime_root = runtime_root

    def install(
        self,
        installation: Installation,
        sdk_path: Path | None = None,
    ) -> None:
        venv_dir = installation.root / ".venv"
        python = self._ensure_venv(venv_dir)

        projects: list[Path] = []
        if sdk_path is not None and self._has_project_file(sdk_path):
            projects.append(sdk_path)

        for pack in installation.packs:
            artifact = self._artifacts.get_artifact(pack)
            if artifact is None:
                continue
            projects.extend(self._find_projects(artifact))

        # Include all runtime projects (api, engine, store, etc.) to satisfy
        # dependencies declared by packs like boot.
        if self._runtime_root is not None:
            projects.extend(self._find_projects(self._runtime_root))

        if projects:
            self._pip_install_all(python, projects)

    def _ensure_venv(self, path: Path) -> Path:
        python = ensure_venv(path)
        upgrade_pip(python)
        return python

    def _find_projects(self, pack_dir: Path) -> list[Path]:
        if not pack_dir.is_dir():
            return []
        if self._has_project_file(pack_dir):
            return [pack_dir]
        projects: list[Path] = []
        for child in sorted(pack_dir.iterdir()):
            if child.is_dir() and self._has_project_file(child):
                projects.append(child)
        return projects

    @staticmethod
    def _has_project_file(directory: Path) -> bool:
        return (
            (directory / "pyproject.toml").exists()
            or (directory / "setup.py").exists()
            or (directory / "setup.cfg").exists()
        )

    def _pip_install_all(self, python: Path, projects: list[Path]) -> None:
        cmd = [str(python), "-m", "pip", "install"]
        for proj in projects:
            cmd.extend(["-e", str(proj)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            warnings.warn(f"pip install failed:\n{result.stderr.strip()}")
