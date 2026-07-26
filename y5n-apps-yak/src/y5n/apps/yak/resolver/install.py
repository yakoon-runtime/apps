"""Artifact install workflow — resolve + install from configured sources."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from y5n.apps.yak.resolver.artifact import DirectorySource

_INSTALLED: list[str] = []


def _collect_roots(artifact_root: Path | None) -> list[Path]:
    """Collect artifact roots to search — context-local first, then global."""
    if artifact_root is not None:
        return [artifact_root]

    from y5n.apps.yak.hosts.cli.cwd import find_context_root

    roots: list[Path] = []

    # Context-local artifacts
    ctx = find_context_root()
    if ctx is not None:
        local = ctx / ".yak" / "artifacts"
        local.mkdir(parents=True, exist_ok=True)
        roots.append(local)

    # Global artifact cache (always available)
    for d in [Path.home() / ".yak" / "artifacts", Path.home() / ".yak" / "cache" / "artifacts"]:
        d.mkdir(parents=True, exist_ok=True)
        if d not in roots:
            roots.append(d)

    return roots


def install_artifact(
    name: str,
    target_root: Path | None = None,
    artifact_root: Path | None = None,
    _seen: set[str] | None = None,
) -> bool:
    if _seen is None:
        _seen = set()

    if name in _seen:
        return True
    _seen.add(name)

    roots = _collect_roots(artifact_root)

    # Search all roots for the artifact
    artifact = None
    for root in roots:
        source = DirectorySource(root)
        candidate = source.resolve(name)
        if candidate is not None:
            artifact = candidate
            break

    if artifact is None:
        return False

    if artifact.is_meta():
        all_ok = True
        for dep in artifact.dependencies:
            if not install_artifact(dep, target_root, artifact_root, _seen):
                all_ok = False
        return all_ok

    if target_root is not None:
        venv = target_root / ".venv"
        if not (venv / "bin" / "python").exists():
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                check=True, capture_output=True,
            )
        python = venv / "bin" / "python"
    else:
        python = Path(sys.executable)

    _INSTALLED.append(name)
    return _install_one(artifact, python)


def _install_one(artifact, python: Path) -> bool:
    wheel = artifact.package_file
    if wheel is None or not wheel.exists():
        return False

    result = subprocess.run(
        [str(python), "-m", "pip", "install", str(wheel)],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def resolve_external_dependencies(target_root: Path | None = None) -> bool:
    return True
