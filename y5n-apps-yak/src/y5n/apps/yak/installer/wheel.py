"""WheelInstaller — install Python wheels from artifacts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from y5n.apps.yak.resolver.artifact import Artifact


def install_wheel(artifact: Artifact, target_venv: Path | None = None) -> bool:
    """Install a wheel artifact into a Python environment.

    Args:
        artifact: The resolved artifact.
        target_venv: Path to a virtual environment. If None, uses the current
                     Python interpreter.

    Returns:
        True if installation succeeded.
    """
    python = (target_venv / "bin" / "python") if target_venv else Path(sys.executable)
    wheel = artifact.package_file

    if not wheel.exists():
        return False

    result = subprocess.run(
        [str(python), "-m", "pip", "install", str(wheel)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
