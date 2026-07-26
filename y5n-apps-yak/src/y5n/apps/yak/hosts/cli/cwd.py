from __future__ import annotations

from pathlib import Path


def find_installation_from_cwd() -> str | None:
    """Detect installation name from current or parent directory."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        state = parent / ".yak" / "state.toml"
        if state.exists():
            import tomllib

            with open(state, "rb") as f:
                data = tomllib.load(f)
            return data.get("installation", {}).get("name")
    return None


def find_installation_path() -> Path | None:
    """Return the root path of the installation containing CWD."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".yak" / "state.toml").exists():
            return parent
        if (parent / ".yak" / "installation.yml").exists():
            return parent
    return None
