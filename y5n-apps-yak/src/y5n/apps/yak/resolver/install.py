"""Artifact install workflow — resolve + install from configured sources."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from y5n.apps.yak.resolver.artifact import DirectorySource

_INSTALLED: list[str] = []


def _collect_roots(artifact_root: Path | None) -> list[Path]:
    if artifact_root is not None:
        return [artifact_root]

    from y5n.apps.yak.hosts.cli.cwd import find_context_root

    roots: list[Path] = []

    ctx = find_context_root()
    if ctx is not None:
        local = ctx / ".yak" / "artifacts"
        local.mkdir(parents=True, exist_ok=True)
        roots.append(local)

    # Shared read-only fallback for pre-built meta packages
    for d in [
        Path.home() / ".yak" / "cache" / "artifacts",
        Path.home() / ".yak" / "artifacts",
    ]:
        if d.is_dir() and d not in roots:
            roots.append(d)

    return roots


_FORCE = False


def _all_sources(extra_sources: list[str] | None = None) -> list:
    """Collect all source implementations."""
    from y5n.apps.yak.resolver.artifact import DirectorySource

    sources: list = []

    # Local roots
    for root in _collect_roots(None):
        sources.append(DirectorySource(root))

    # Remote sources (github:owner/repo, etc.)
    for src in extra_sources or []:
        if src.startswith("github:") or "/" in src:
            from y5n.apps.yak.resolver.github import GithubReleaseRepository

            sources.append(GithubReleaseRepository(src))

    return sources


def find_artifact(
    name: str,
    artifact_root: Path | None = None,
    sources: list[str] | None = None,
) -> Artifact | None:
    """Resolve an artifact by name from all configured sources."""
    for source in _all_sources(sources):
        candidate = source.resolve(name)
        if candidate is not None:
            return candidate
    return None


def install_artifact(
    name: str,
    target_root: Path | None = None,
    artifact_root: Path | None = None,
    force: bool = False,
    sources: list[str] | None = None,
    _seen: set[str] | None = None,
) -> bool:
    global _FORCE
    if force:
        _FORCE = True

    if _seen is None:
        _seen = set()

    if name in _seen:
        return True
    _seen.add(name)

    # Search all sources for the artifact
    artifact = find_artifact(name, artifact_root=artifact_root, sources=sources)
    if artifact is None:
        return False

    if artifact.is_meta():
        all_ok = True
        for dep in artifact.dependencies:
            if not install_artifact(dep, target_root, artifact_root, _FORCE, _seen):
                all_ok = False
        return all_ok

    if target_root is not None:
        venv = target_root / ".venv"
        if not (venv / "bin" / "python").exists():
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                check=True,
                capture_output=True,
            )
        python = venv / "bin" / "python"
    else:
        python = Path(sys.executable)

    # Check fingerprint — skip if unchanged
    if not _FORCE and _fingerprint_matches(artifact, target_root):
        return True

    _INSTALLED.append(name)
    ok = _install_one(artifact, python)
    if ok and target_root is not None:
        _write_fingerprint(artifact, target_root)
    return ok


def _fingerprints_dir(target_root: Path | None) -> Path | None:
    if target_root is None:
        return None
    d = target_root / ".yak" / "cache" / "fingerprints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fingerprint_path(artifact, target_root: Path | None) -> Path | None:
    d = _fingerprints_dir(target_root)
    if d is None:
        return None
    return d / artifact.name


def _fingerprint_matches(artifact, target_root: Path | None) -> bool:
    fp = _fingerprint_path(artifact, target_root)
    if fp is None or not fp.exists():
        return False
    if not artifact.fingerprint:
        return False
    return fp.read_text().strip() == artifact.fingerprint


def _write_fingerprint(artifact, target_root: Path | None) -> None:
    fp = _fingerprint_path(artifact, target_root)
    if fp is None or not artifact.fingerprint:
        return
    fp.write_text(artifact.fingerprint)


def _install_one(artifact, python: Path) -> bool:
    wheel = artifact.package_file
    if wheel is None or not wheel.exists():
        return False

    cmd = [str(python), "-m", "pip", "install", "--no-deps"]
    if _FORCE:
        cmd.append("--force-reinstall")
    cmd.append(str(wheel))

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Install deps normally (pip resolves PyPI packages)
    if result.returncode == 0:
        dep_cmd = [str(python), "-m", "pip", "install", str(wheel)]
        subprocess.run(dep_cmd, capture_output=True, text=True)

    return result.returncode == 0


def resolve_external_dependencies(target_root: Path | None = None) -> bool:
    return True
