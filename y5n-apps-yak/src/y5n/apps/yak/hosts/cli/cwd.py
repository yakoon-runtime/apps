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


def find_context_root() -> Path | None:
    """Walk up from CWD looking for a Yak context marker."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".yak" / "state.toml").exists():
            return parent
        if (parent / ".yak" / "context.toml").exists():
            return parent
    return None


def find_installation_path() -> Path | None:
    return find_context_root()
def default_artifact_dir() -> Path | None:
    """Return the default artifact directory for the current context."""
    ctx = find_context_root()
    if ctx is None:
        return None
    d = ctx / ".yak" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d

