from __future__ import annotations

import subprocess
from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path


def run(args, mgr) -> None:
    path = Path(args.target).resolve() if args.target else find_installation_path()
    if path is None:
        print("No installation specified. cd into one or pass a directory.")
        return

    python = path / ".venv" / "bin" / "python"
    subprocess.run([str(python), "-m", "y5n.apps.shell"], cwd=path)
