"""BootstrapWorkflow — orchestrate bootstrap tasks."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.bootstrap.tasks import (
    CreateVenvTask,
    InstallProjectsTask,
    MaterializeWorkspaceTask,
    SummaryTask,
    VerifyTask,
)


def bootstrap(root: Path | None = None) -> bool:
    """Run the full bootstrap workflow.

    Args:
        root: Repository root. Auto-detected if None.

    Returns:
        True if all tasks succeeded.
    """
    if root is None:
        root = _find_repo_root()
    if root is None:
        print("Error: not a Yakoon repository")
        return False

    venv_python = root / ".venv" / "bin" / "python"

    steps = [
        ("Virtual environment", CreateVenvTask(root)),
        ("Install projects", InstallProjectsTask(root, venv_python)),
        ("Workspace", MaterializeWorkspaceTask(root)),
        ("Verify", VerifyTask(venv_python)),
    ]

    all_ok = True
    for label, task in steps:
        label = f"  {label:<24}"
        try:
            ok = task.run()
            if ok:
                print(f"✓ {label}")
            else:
                print(f"✘ {label}")
                all_ok = False
        except Exception as e:
            print(f"✘ {label}  {e}")
            all_ok = False

    if all_ok:
        SummaryTask(root, venv_python).run()

    return all_ok


def _find_repo_root() -> Path | None:
    """Walk up from CWD looking for a Yakoon repository marker."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "runtime").is_dir() and (parent / "pyproject.toml").exists():
            return parent
    return None
