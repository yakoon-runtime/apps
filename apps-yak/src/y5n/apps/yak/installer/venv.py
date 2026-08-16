"""Shared virtualenv handling for installs.

Both install paths — wheels (``resolver.install``) and editable source
projects (``installer.installer``) — need a venv at the target root.
This is the single place that creates it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def ensure_venv(path: Path) -> tuple[Path, bool]:
    """Create a venv at ``path`` if missing; return (python, created)."""
    created = not (path / "bin" / "python").exists()
    if created:
        subprocess.run(
            [sys.executable, "-m", "venv", str(path)],
            check=True,
            capture_output=True,
        )
    return path / "bin" / "python", created


def upgrade_pip(python: Path) -> None:
    """Upgrade pip in the venv to the bundled interpreter's version.

    Only run once, right after the venv is created — pip in a fresh venv
    is the bundled version already.
    """
    subprocess.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        capture_output=True,
    )
