"""Bootstrap tasks — each task is a single responsibility."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class CreateVenvTask:
    """Create a Python virtual environment at the given path."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def run(self) -> bool:
        venv = self._root / ".venv"
        if (venv / "bin" / "python").exists():
            return True  # already exists — idempotent

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

    def __init__(self, root: Path, venv_python: Path) -> None:
        self._root = root
        self._python = venv_python

    def run(self) -> bool:
        projects = self._discover()
        if not projects:
            return False

        cmd = [str(self._python), "-m", "pip", "install"]
        for proj in projects:
            cmd.extend(["-e", str(proj)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    def _discover(self) -> list[Path]:
        families = ["runtime", "sdk", "packs", "apps"]
        projects: list[Path] = []
        seen: set[Path] = set()

        for family in families:
            family_dir = self._root / family
            if not family_dir.is_dir():
                continue
            for child in sorted(family_dir.iterdir()):
                if not child.is_dir():
                    continue
                if not (child / "pyproject.toml").exists():
                    continue
                if child in seen:
                    continue
                seen.add(child)
                projects.append(child)
        return projects


class MaterializeWorkspaceTask:
    """Materialize the development workspace from an environment file."""

    def __init__(self, root: Path, env_file: Path | None = None) -> None:
        self._root = root
        self._env_file = env_file

    def run(self) -> bool:
        if self._env_file is None or not self._env_file.exists():
            return False

        import yaml
        data = yaml.safe_load(self._env_file.read_text())
        ws = data.get("workspace", {})
        ws_path = ws.get("path", "workspace")
        packs_raw = ws.get("packs", [])
        mounts_raw = ws.get("mounts", [])

        workspace = self._root / ws_path
        if workspace.exists():
            return True

        workspace.mkdir(parents=True, exist_ok=True)

        from y5n.apps.yak.distribution.models import Mount, PackName
        from y5n.apps.yak.repository.artifact import DirectoryArtifactStore as Store
        from y5n.apps.yak.workspace.materializer import Materializer

        materializer = Materializer(
            Store(
                self._root / "packs",
                self._root / "runtime",
                self._root / "apps",
                self._root / "sdk" / "y5n-sdk-python",
            )
        )

        materializer.materialize(
            workspace,
            "dev",
            [PackName(p) for p in packs_raw],
            mounts=[Mount(pack=PackName(m["pack"]), target=m["target"]) for m in mounts_raw],
        )

        (self._root / "yakoon-runtime.yml").write_text(
            f"workspace_path: {ws_path}\n"
            "listen:\n  host: 127.0.0.1\n  port: 9100\n"
        )

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

        print(f"Python      : {py_version}")
        print(f"Venv        : {self._root / '.venv'}")
        print(f"Workspace   : {self._root / 'workspace'}")
        print(f"Projects    : {len(projects_found)}")
        print()
        print("Bootstrap completed. Run 'pytest' or 'code .' to start developing.")
        return True
