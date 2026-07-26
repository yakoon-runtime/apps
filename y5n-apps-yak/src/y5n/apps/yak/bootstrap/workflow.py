"""BootstrapWorkflow — orchestrate bootstrap tasks."""

from __future__ import annotations

from pathlib import Path

import yaml

from y5n.apps.yak.bootstrap.tasks import (
    CreateVenvTask,
    InstallProjectsTask,
    MaterializeWorkspaceTask,
    SummaryTask,
    VerifyTask,
)


def bootstrap(root: Path | None = None, force: bool = False, check: bool = False) -> bool:
    if root is None:
        root = _find_repo_root()
    if root is None:
        print("Error: not a Yakoon repository")
        return False

    venv_python = root / ".venv" / "bin" / "python"

    # Determine bootstrap environment from yak.yml
    env_name = "dev"
    artifacts_dir = root / "apps" / "y5n-apps-yak" / "artifacts"

    for candidate in [root / "yak.yml", root / "apps" / "y5n-apps-yak" / "yak.yml"]:
        if candidate.exists():
            try:
                cfg = yaml.safe_load(candidate.read_text())
                bs = cfg.get("bootstrap", {})
                env_name = bs.get("environment", env_name)
                art_rel = bs.get("artifacts", "")
                if art_rel:
                    artifacts_dir = (root / art_rel).resolve()
            except Exception:
                pass
            break

    env_file = artifacts_dir / f"{env_name}.yml"
    if not env_file.exists():
        print(f"Error: bootstrap environment '{env_name}' not found at {env_file}")
        return False

    tasks = [
        ("Virtual environment", CreateVenvTask(root, force=force)),
        ("Install projects", InstallProjectsTask(root, venv_python, force=force)),
        ("Workspace", MaterializeWorkspaceTask(root, env_file=env_file, force=force)),
    ]

    if not check:
        all_ok = True
        for label, task in tasks:
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
            ok = VerifyTask(venv_python).run()
            print(f"  {'✓' if ok else '✘'} {'Verify':<24}")
            SummaryTask(root, venv_python).run()
    else:
        # --check mode: just verify what's present
        print("  Repo        ✓" if root else "  Repo        ✘")
        print("  .venv       ✓" if (root / ".venv" / "bin" / "python").exists() else "  .venv       ✘")
        print("  Workspace   ✓" if (root / "workspace").exists() else "  Workspace   ✘")

    return True


def _find_repo_root() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "runtime").is_dir() and (parent / "pyproject.toml").exists():
            return parent
    return None
