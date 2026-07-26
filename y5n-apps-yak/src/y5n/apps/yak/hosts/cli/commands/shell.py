"""yak shell — open the Yakoon shell."""

from __future__ import annotations

import subprocess
from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path


def run(args, mgr) -> None:
    path = find_installation_path()
    if path is None:
        print("Not inside a Yak installation.")
        print("Run 'yak install' first or cd into one.")
        return

    log_dir = path / ".yak" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "shell.log"

    python = path / ".venv" / "bin" / "python"
    with open(log_file, "a") as lf:
        subprocess.run(
            [str(python), "-m", "y5n.apps.shell"],
            cwd=path, stderr=lf,
        )
