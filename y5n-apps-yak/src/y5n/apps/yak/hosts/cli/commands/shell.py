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

    python = path / ".venv" / "bin" / "python"
    subprocess.run([str(python), "-m", "y5n.apps.shell"], cwd=path)
