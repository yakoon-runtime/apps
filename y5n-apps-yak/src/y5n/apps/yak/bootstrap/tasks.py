"""Bootstrap tasks — each task is a single responsibility."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class CreateVenvTask:
    """Create a Python virtual environment at the given path."""

    def __init__(self, root: Path, force: bool = False) -> None:
        self._root = root
        self._force = force

    def run(self) -> bool:
        venv = self._root / ".venv"
        if not self._force and (venv / "bin" / "python").exists():
            return True

        subprocess.run(
            [sys.executable, "-m", "venv", str(venv)],
            check=True,
            capture_output=True,
        )
        python = venv / "bin" / "python"
        subprocess.run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            capture_output=True,
        )
        return True


class InstallProjectsTask:
    """Discover and install all y5n-* projects into the virtual environment."""

    def __init__(self, root: Path, venv_python: Path, force: bool = False) -> None:
        self._root = root
        self._python = venv_python
        self._force = force

    def run(self) -> bool:
        projects = self._discover()
        if not projects:
            return False

        # Idempotent: skip if all projects are already installed
        if not self._force:
            check = subprocess.run(
                [str(self._python), "-m", "pip", "list", "--format=columns"],
                capture_output=True,
                text=True,
            )
            installed = check.stdout if check.returncode == 0 else ""
            all_installed = all(p.name in installed for p in projects)
            if all_installed:
                return True

        cmd = [str(self._python), "-m", "pip", "install"]
        for proj in projects:
            cmd.extend(["-e", str(proj)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    def _discover(self) -> list[Path]:
        from y5n.apps.yak.installer.installer import platform_projects

        return platform_projects(self._root)


class MaterializeWorkspaceTask:
    """Materialize the development workspace from .yak/environment.yml."""

    def __init__(self, root: Path, force: bool = False) -> None:
        self._root = root
        self._force = force

    def run(self) -> bool:
        from y5n.apps.yak.environment.io import load
        from y5n.apps.yak.workspace.materializer import Materializer

        env = load(self._root)
        if env is None:
            return False

        ws_path = env.workspace_path
        workspace = self._root / ws_path
        if workspace.exists():
            if not self._force:
                print("    Workspace already exists (use --force to recreate)")
                return True
            import shutil

            shutil.rmtree(workspace)

        workspace.mkdir(parents=True, exist_ok=True)

        materializer = Materializer()
        structure_dir = self._root / env.workspace_path
        materializer.materialize(structure_dir, "dev", mounts=list(env.mounts))

        return True


class VerifyTask:
    """Verify that all required platform components are importable."""

    def __init__(self, venv_python: Path) -> None:
        self._python = venv_python

    def run(self) -> bool:
        code = (
            "import y5n.runtime.api; "
            "import y5n.runtime.engine; "
            "import y5n.sdk; "
            "import y5n.apps.yak"
        )
        result = subprocess.run(
            [str(self._python), "-c", code],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0


class SummaryTask:
    """Print the bootstrap summary."""

    def __init__(self, root: Path, venv_python: Path) -> None:
        self._root = root
        self._python = venv_python

    def run(self) -> bool:
        result = subprocess.run(
            [str(self._python), "--version"],
            capture_output=True,
            text=True,
        )
        py_version = result.stdout.strip()

        projects_found = InstallProjectsTask(self._root, self._python)._discover()

        print(f"  Python      : {py_version}")
        print(f"  Venv        : {self._root / '.venv'}")
        print(f"  Workspace   : {self._root / 'workspace'}")
        print(f"  Projects    : {len(projects_found)}")
        print()
        print("  Bootstrap completed. Run 'pytest' or 'code .' to start developing.")
        return True
