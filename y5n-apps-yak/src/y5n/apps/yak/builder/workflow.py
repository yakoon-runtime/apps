"""BuildWorkflow — discover project, select builder, build, cache."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.protocol import Builder
from y5n.apps.yak.builder.python import PythonBuildProvider


def _find_project_root(cwd: Path | None = None) -> Path | None:
    if cwd is None:
        cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text()
            if "[build-system]" in text and "build-backend" in text:
                return parent
    return None


def _select_builder(project_dir: Path) -> Builder | None:
    candidates: list[Builder] = [PythonBuildProvider()]
    for b in candidates:
        if b.detect(project_dir):
            return b
    return None


def build(project_dir: Path | None = None, output_dir: Path | None = None) -> bool:
    from y5n.apps.yak.hosts.cli.cwd import default_artifact_dir

    if output_dir is None:
        output_dir = default_artifact_dir()
        if output_dir is None:
            print("Error: no default artifact directory found")
            return False

    if project_dir is not None:
        project_dir = project_dir.resolve()
    else:
        project_dir = _find_project_root()
    if project_dir is None:
        print("Error: no buildable project found. Specify a path or cd into one.")
        return False

    builder = _select_builder(project_dir)
    if builder is None:
        print("Error: no builder found for this project")
        return False

    print(f"Builder : {builder.name()}")
    print(f"Project : {project_dir}")

    info = builder.build(project_dir, output_dir)
    if info is None:
        print("Error: build failed")
        return False

    print(f"Artifact: {output_dir / info.filename}")
    print(f"Name    : {info.name}")
    print(f"Version : {info.version}")
    print(f"Host    : {info.host}")
    return True
