"""yak bootstrap — prepare a Yakoon repository for development.

Bootstrapping installs the platform from the local sources (editable)
into the source checkout. It is the same installation model as
``yak install`` (released artifacts); only the platform's origin and the
workspace layout differ (``workspace/structure`` instead of
``structure``). The result is a full installation: ``.yak/`` with
environment.yml, state.toml, deployment.yml and components/.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    root = _find_repo_root()
    if root is None:
        print("Error: not a Yakoon repository")
        return

    if getattr(args, "check", False):
        _check(root)
        return

    if getattr(args, "force", False):
        for stale in (root / ".venv", root / "workspace"):
            if stale.exists():
                shutil.rmtree(stale)

    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    ui.title("Bootstrapping Yakoon")
    mgr.install(root, ui=ui, workspace_path="workspace/structure")
    print(f"  Yakoon ready for development at {root}")


def _check(root: Path) -> None:
    print(f"  Repo        ✓" if root else "  Repo        ✘")
    print(
        "  .venv       ✓"
        if (root / ".venv" / "bin" / "python").exists()
        else "  .venv       ✘"
    )
    print("  Workspace   ✓" if (root / "workspace").exists() else "  Workspace   ✘")


def _find_repo_root() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "runtime").is_dir() and (parent / "pyproject.toml").exists():
            return parent
    return None
