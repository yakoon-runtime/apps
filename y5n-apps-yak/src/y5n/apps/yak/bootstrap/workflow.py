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


def bootstrap(
    root: Path | None = None, force: bool = False, check: bool = False
) -> bool:
    if root is None:
        root = _find_repo_root()
    if root is None:
        print("Error: not a Yakoon repository")
        return False

    venv_python = root / ".venv" / "bin" / "python"

    # The minimal platform environment: no packs, no mounts. Capabilities
    # are composed afterwards with `yak add` — the same as `yak install`.
    from y5n.apps.yak.environment.io import save
    from y5n.apps.yak.environment.models import Environment

    save(
        Environment(name=root.name or "yakoon", workspace_path="workspace/structure"),
        root,
    )

    tasks = [
        ("Virtual environment", CreateVenvTask(root, force=force)),
        ("Install platform", InstallProjectsTask(root, venv_python, force=force)),
        ("Workspace", MaterializeWorkspaceTask(root, force=force)),
    ]

    if not check:
        all_ok = True
        for label, task in tasks:
            try:
                ok = task.run()
                if not ok:
                    all_ok = False
                print(f"  {'✓' if ok else '✘'} {label:<24}")
            except Exception as e:
                print(f"  ✘ {label:<24}  {e}")
                all_ok = False

        if all_ok:
            ok = VerifyTask(venv_python).run()
            print(f"  {'✓' if ok else '✘'} {'Verify':<24}")
            SummaryTask(root, venv_python).run()
    else:
        # --check mode: just verify what's present
        print("  Repo        ✓" if root else "  Repo        ✘")
        print(
            "  .venv       ✓"
            if (root / ".venv" / "bin" / "python").exists()
            else "  .venv       ✘"
        )
        print("  Workspace   ✓" if (root / "workspace").exists() else "  Workspace   ✘")

    return True


def _find_repo_root() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "runtime").is_dir() and (parent / "pyproject.toml").exists():
            return parent
    return None
