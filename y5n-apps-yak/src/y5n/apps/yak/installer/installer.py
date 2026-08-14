from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

from y5n.apps.yak.installation.models import Installation
from y5n.apps.yak.installer.venv import ensure_venv, upgrade_pip


class Installer:
    def install(self, installation: Installation) -> None:
        venv_dir = installation.root / ".venv"
        python = self._ensure_venv(venv_dir)

        projects: list[Path] = []
        for component in installation.components:
            if component.mode != "source":
                continue
            if not component.source:
                continue
            projects.extend(self._find_projects(Path(component.source)))

        # Deduplicate while keeping order.
        seen: set[Path] = set()
        unique: list[Path] = []
        for proj in projects:
            resolved = proj.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)

        if unique:
            self._pip_install_all(python, unique)

    def _ensure_venv(self, path: Path) -> Path:
        python = ensure_venv(path)
        upgrade_pip(python)
        return python

    def _find_projects(self, pack_dir: Path) -> list[Path]:
        if not pack_dir.is_dir():
            return []
        if self._has_project_file(pack_dir):
            return [pack_dir]
        # The source may be a content directory (``structure/``) inside a
        # project whose own project file lives at the parent (e.g. a pack
        # that is also a Python package).
        parent = pack_dir.parent
        if parent.is_dir() and self._has_project_file(parent):
            return [parent]
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
