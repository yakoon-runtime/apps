"""PostgreSQL infrastructure client of an installation (thin).

Delegates the actual database work to the runtime store's admin
primitive, running in the installation venv. Nothing here knows
``asyncpg``, DSNs or ``CREATE DATABASE`` — the store component is the one
PostgreSQL expert. This module only knows where the installation's python
lives and how to hand a DSN to the admin entrypoint.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ADMIN_MODULE = "y5n.runtime.store.event.backends.postgres.admin"


def ensure_database(installation: Path, dsn: str) -> bool:
    """Ensure the target database exists; True when it was created.

    Raises ``RuntimeError`` when the admin operation fails — the original
    error is carried along, never swallowed. ``installation`` is the
    environment root owning ``.venv``.
    """
    python = installation / ".venv" / "bin" / "python"
    if not python.is_file():
        raise RuntimeError(f"No environment python at {python} — run 'yak install' first")

    result = subprocess.run(
        [str(python), "-m", ADMIN_MODULE, dsn],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "database creation failed")
    return "created" in result.stdout