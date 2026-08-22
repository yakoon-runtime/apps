"""Deploy helper — a writable repository receives a resource (ADR-20).

The read side resolves through catalogs and an index; this module only
serves the write side: publishing a local artifact to the system-wide
store and deploying it as a release of its owning repository.
"""

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
    """Publish a published artifact as a GitHub release asset (ADR-24).

    Reads only from the system-wide store (``~/.yak/artifacts/``) — an
    artifact must be published first (``yak publish``). The receiving
    repository gets the artifact as a release, so the build is physically
    available. Entering it into a distribution (what is installable) is the
    distribution write, separate from this physical publish. Returns None
    when the artifact is not published, otherwise the publish result.
    """
    from y5n.apps.yak.resolver.github import GithubReleaseRepository

    if not target.startswith("github:"):
        raise RuntimeError(
            f"Unknown repository: {target}\n"
            "Use an inline spec like 'github:owner/repo'."
        )

    published = DirectorySource(Path.home() / ".yak" / "artifacts").resolve(name)
    if published is None or published.path is None:
        return None

    return GithubReleaseRepository(target).deploy(name, published.path)
