"""BuildWorkflow — discover projects under source, build, cache."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.protocol import Builder
from y5n.apps.yak.builder.python import PythonBuildProvider


def _find_buildable_projects(root: Path) -> list[Path]:
    """Recursively find all buildable projects under root."""
    projects: list[Path] = []

    if not root.is_dir():
        return projects

    # A buildable project has a pyproject.toml with a build-system; the
    # presence of mount.toml/structure is irrelevant to buildability.
    pyproj = root / "pyproject.toml"
    if pyproj.exists() and _is_buildable_pyproject(pyproj):
        projects.append(root)

    # Recurse into subdirectories
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        projects.extend(_find_buildable_projects(child))

    return projects


def _is_buildable_pyproject(path: Path) -> bool:
    try:
        text = path.read_text()
        return "[build-system]" in text and "build-backend" in text
    except Exception:
        return False


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
            print("Error: no Yak context found.")
            print(
                "Run 'yak init' first, then 'yak build <source>' from within the context."
            )
            return False

    if project_dir is None:
        print("Error: no source path given.")
        print("Usage: yak build <source-path>  (e.g. yak build ../runtime)")
        return False

    source = project_dir.resolve()
    projects = _find_buildable_projects(source)

    if not projects:
        print(f"No buildable projects found under: {source}")
        return False

    print(f"Found {len(projects)} build project(s).\n")

    all_ok = True
    for p in projects:
        builder = _select_builder(p)
        if builder is None:
            print(f"  ✘ {p.name}  (no builder)")
            all_ok = False
            continue

        print(
            f"  Building {p.relative_to(source.parent) if source.parent else p.name} ..."
        )
        info = builder.build(p, output_dir)
        if info is None:
            print(f"  ✘ {p.name}")
            all_ok = False
        else:
            print(f"  ✓ {info.name} {info.version}")

    return all_ok
