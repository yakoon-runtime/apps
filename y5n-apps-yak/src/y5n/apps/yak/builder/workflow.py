"""BuildWorkflow — discover project, select builder, build, cache."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.protocol import Builder
from y5n.apps.yak.builder.python import PythonBuildProvider


def _find_project_root() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            # Ensure this is a buildable project (has [build-system])
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


def build(output_dir: Path | None = None) -> bool:
    if output_dir is None:
        from y5n.apps.yak.hosts.cli.cwd import default_artifact_dir

        output_dir = default_artifact_dir()
        if output_dir is None:
            print("Error: no Yak context found. Run 'yak init' first.")
            return False

    project_dir = _find_project_root()
    if project_dir is None:
        print("Error: no buildable project found. Run 'yak build' from a project directory.")
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
