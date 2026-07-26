"""Artifact install workflow — resolve + install from configured sources."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.resolver.artifact import DirectorySource


def install_artifact(
    name: str,
    artifact_root: Path | None = None,
) -> bool:
    """Resolve and install an artifact by name.

    Args:
        name: Artifact name (e.g. 'y5n-runtime-api').
        artifact_root: Directory containing .artifact folders.
                       Defaults to ~/.yak/cache/artifacts/.

    Returns:
        True if resolution and installation succeeded.
    """
    if artifact_root is None:
        artifact_root = Path.home() / ".yak" / "cache" / "artifacts"

    source = DirectorySource(artifact_root)
    artifact = source.resolve(name)
    if artifact is None:
        return False

    from y5n.apps.yak.installer.wheel import install_wheel

    return install_wheel(artifact)
