"""yak shell — open the Yakoon shell."""

from __future__ import annotations

import subprocess

from y5n.apps.yak.hosts.cli.cwd import find_runtime_root


def run(args, mgr) -> None:
    path = find_runtime_root()
    if path is None:
        print("Not inside a Yak context or installation.")
        print("Run 'yak install' first or cd into one.")
        return

    python = path / ".venv" / "bin" / "python"

    # Check if shell is installed
    check = subprocess.run(
        [str(python), "-c", "import y5n.apps.shell"],
        capture_output=True,
    )
    if check.returncode != 0:
        print("Yakoon shell is not installed in this context.")
        print("Run 'yak install shell' to install it.")
        return

    subprocess.run([str(python), "-m", "y5n.apps.shell"], cwd=path)
