from pathlib import Path


def find_project_root(start: Path) -> Path:
    for parent in start.parents:
        if (parent / "clients").exists():
            return parent
    raise RuntimeError("Project root not found")
