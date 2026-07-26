"""Artifact install workflow — resolve + install from configured sources."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.resolver.artifact import DirectorySource


def install_artifact(
    name: str,
    artifact_root: Path | None = None,
    _seen: set[str] | None = None,
) -> bool:
    if artifact_root is None:
        artifact_root = Path.home() / ".yak" / "cache" / "artifacts"
    if _seen is None:
        _seen = set()

    if name in _seen:
        return True
    _seen.add(name)

    source = DirectorySource(artifact_root)
    artifact = source.resolve(name)
    if artifact is None:
        return False

    if artifact.is_meta():
        all_ok = True
        for dep in artifact.dependencies:
            if not install_artifact(dep, artifact_root, _seen):
                all_ok = False
        return all_ok

    from y5n.apps.yak.installer.wheel import install_wheel

    return install_wheel(artifact)
