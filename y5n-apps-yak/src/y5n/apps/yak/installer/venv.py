"""Shared virtualenv handling for installs.

Both install paths — wheels (``resolver.install``) and editable source
projects (``installer.installer``) — need a venv at the target root.
This is the single place that creates it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def ensure_venv(path: Path) -> Path:
    """Create a venv at ``path`` if missing; return its python binary."""
    if not (path / "bin" / "python").exists():
        subprocess.run(
            [sys.executable, "-m", "venv", str(path)],
            check=True,
            capture_output=True,
        )
    return path / "bin" / "python"


def upgrade_pip(python: Path) -> None:
    """Upgrade pip in the venv to the bundled interpreter's version."""
    subprocess.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        capture_output=True,
    )
