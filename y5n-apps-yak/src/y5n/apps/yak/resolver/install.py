"""Artifact store roots — the local write-side store (ADR-20).

Resolution no longer lives here: components resolve through source
catalogs and the merged index. This module keeps only the local store
roots used by the publish/deploy write side.
"""

from __future__ import annotations

from pathlib import Path


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
