"""Publish artifacts to local store or remote repositories."""

from __future__ import annotations

import shutil
from pathlib import Path

from y5n.apps.yak.resolver.artifact import DirectorySource
from y5n.apps.yak.resolver.install import _collect_roots


def _find_artifact(name: str) -> Path | None:
    """Find artifact in context-local .yak/artifacts/."""
    for root in _collect_roots(None):
        source = DirectorySource(root)
        artifact = source.resolve(name)
        if artifact is not None and artifact.path is not None:
            return artifact.path
    return None


def publish_local(name: str) -> Path | None:
    """Copy artifact to ~/.yak/artifacts/."""
    src = _find_artifact(name)
    if src is None:
        return None

    target_dir = Path.home() / ".yak" / "artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / src.name
    if dest.resolve() == src.resolve():
        # Already in the global store — publishing is a no-op.
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def deploy_artifact(name: str, target: str) -> bool | None:
    """Deploy a published artifact to a remote repository.

    Reads only from the system-wide store (``~/.yak/artifacts/``) — an
    artifact must be published first (``yak publish``). Returns None when
    the artifact is not published, otherwise the deploy result.
    """
    from y5n.apps.yak.resolver.install import repository_for

    repository = repository_for(target)
    if repository is None:
        raise RuntimeError(
            f"Unknown repository: {target}\n"
            "Define it in .yak/context.toml under [repositories.<name>]\n"
            "or use an inline spec like 'github:owner/repo'."
        )

    published = DirectorySource(Path.home() / ".yak" / "artifacts").resolve(name)
    if published is None or published.path is None:
        return None

    return repository.deploy(name, published.path)
