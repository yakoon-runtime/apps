"""Install the Python candidates of a resolved installation.

Source and artifact are different origins of the same component; for
pip they are different install forms of the same Python distribution.
Both are presented in ONE pip transaction so pip resolves the whole
graph at once — never two separate phases that each fail on the other.
A failed pip call raises; an install never reports success with a
broken environment.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from y5n.apps.yak.installer.venv import ensure_venv, upgrade_pip


@dataclass(frozen=True)
class PythonCandidate:
    """One install form of a resolved component for the single pip call.

    Exactly one of ``wheel`` (artifact) or ``project`` (source, editable)
    is set.
    """

    wheel: Path | None = None
    project: Path | None = None


class Installer:
    def install(self, root: Path, candidates: list[PythonCandidate]) -> None:
        """Install all candidates into the environment in one pip transaction.

        Artifact wheels and editable source projects are handed to pip
        together, so it can satisfy every ``Requires-Dist`` from within
        the set. pip stays responsible for Python dependencies — Yak adds
        none.
        """
        python = self._ensure_venv(root / ".venv")
        args: list[str] = []
        for candidate in candidates:
            if candidate.wheel is not None:
                args.append(str(candidate.wheel))
            elif candidate.project is not None:
                for project in self._find_projects(candidate.project):
                    args.extend(["-e", str(project)])
        if not args:
            return
        self._pip_install_all(python, args)

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

    def _pip_install_all(self, python: Path, args: list[str]) -> None:
        cmd = [str(python), "-m", "pip", "install", *args]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pip install failed:\n{result.stderr.strip()}")
