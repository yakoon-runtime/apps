"""Publish artifacts to the user-global artifact store."""

from __future__ import annotations

import shutil
from pathlib import Path

from y5n.apps.yak.resolver.artifact import DirectorySource
from y5n.apps.yak.resolver.install import _collect_roots


def publish_artifact(name: str) -> Path | None:
    """Find artifact in context-local .yak/artifacts/ and copy to ~/.yak/artifacts/.

    Returns the target directory, or None if the artifact wasn't found.
    """
    for root in _collect_roots(None):
        source = DirectorySource(root)
        artifact = source.resolve(name)
        if artifact is not None and artifact.path is not None:
            break
    else:
        return None

    target_dir = Path.home() / ".yak" / "artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)

    dest = target_dir / artifact.path.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(artifact.path, dest)
    return dest
