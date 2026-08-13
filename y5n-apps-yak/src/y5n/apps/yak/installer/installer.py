from __future__ import annotations

import subprocess
from pathlib import Path

from y5n.apps.yak.installation.models import Installation
from y5n.apps.yak.installer.venv import ensure_venv, upgrade_pip
from y5n.apps.yak.pack.models import ToolReference
from y5n.apps.yak.repository.artifact import ArtifactStore

# Map tool names to app directories (package = directory under apps/)
_TOOL_PACKAGES: dict[str, str] = {
    "runtime": "y5n-apps-runtime",
    "shell": "y5n-apps-shell",
    "web": "y5n-apps-web",
    "yak": "y5n-apps-yak",
}

# The minimal platform: the host apps. The runtime family and the SDK are
# platform by family. No packs — capabilities are added with `yak add`.
PLATFORM_TOOLS = [ToolReference("runtime"), ToolReference("yak")]


def resolve_tool(name: str) -> ToolReference | None:
    """Resolve a tool (host app) name like ``shell`` or ``web``."""
    if name in _TOOL_PACKAGES:
        return ToolReference(name)
    return None


def _has_project_file(directory: Path) -> bool:
    return (
        (directory / "pyproject.toml").exists()
        or (directory / "setup.py").exists()
        or (directory / "setup.cfg").exists()
    )


def platform_projects(source_root: Path) -> list[Path]:
    """The minimal platform projects in a source tree.

    The runtime family, the SDK and the host apps — no packs. ``install``
    and ``bootstrap`` both build the platform from this set; they only
    differ in where the projects come from.
    """
    projects: list[Path] = []
    seen: set[Path] = set()

    for base in (source_root / "runtime", source_root / "sdk"):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and _has_project_file(child) and child not in seen:
                seen.add(child)
                projects.append(child)

    for tool in PLATFORM_TOOLS:
        pkg = _TOOL_PACKAGES.get(tool.name)
        if pkg is None:
            continue
        app = source_root / "apps" / pkg
        if app.is_dir() and app not in seen:
            seen.add(app)
            projects.append(app)

    return projects


class Installer:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        apps_root: Path | None = None,
        runtime_root: Path | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._apps_root = apps_root
        self._runtime_root = runtime_root

    def install(
        self,
        installation: Installation,
        tools: list[ToolReference] | None = None,
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

        if tools:
            for tool in tools:
                pkg = self._find_tool(tool.name)
                if pkg is not None:
                    projects.extend(self._find_projects(pkg))

        if projects:
            self._pip_install_all(python, projects)

    def _find_tool(self, name: str) -> Path | None:
        pkg = _TOOL_PACKAGES.get(name)
        if pkg is None or self._apps_root is None:
            return None
        tool_dir = self._apps_root / pkg
        return tool_dir if tool_dir.is_dir() else None

    def has_tool_source(self, name: str) -> bool:
        """Whether a host app's source is available in this manager's roots."""
        return self._find_tool(name) is not None

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
            import warnings

            warnings.warn(f"pip install failed:\n{result.stderr.strip()}")
