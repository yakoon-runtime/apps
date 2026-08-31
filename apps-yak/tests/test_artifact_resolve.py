"""DirectorySource versions: a store may hold several versions of one
artifact. The resolver must select the newest deterministically — the
contract is ``resolve(name) → newest`` (mirroring ``Distribution.latest``)
and never depends on the order the OS reports directories in.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from y5n.apps.yak.resolver.artifact import DirectorySource


def _artifact_dir(
    root: Path, name: str, version: str, *, mount: str = "/opt/x"
) -> Path:
    """An artifact directory named like a built artifact."""
    entry = root / f"{name}-{version}.python.artifact"
    entry.mkdir(parents=True)
    (entry / "artifact.yml").write_text(
        f"name: {name}\nversion: {version}\nkind: package\n"
        f"host: python\nbuilder: python\n"
        f"mount:\n  source: structure\n  path: {mount}\n"
    )
    return entry


def test_resolve_picks_newest_numeric_version():
    """0.10.0 is newer than 0.2.0 despite being 'smaller' lexically."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old = _artifact_dir(root, "acme-pack", "0.2.0")
        newest = _artifact_dir(root, "acme-pack", "0.10.0")
        mid = _artifact_dir(root, "acme-pack", "0.8.0")

        resolved = DirectorySource(root).resolve("acme-pack")
        assert resolved is not None
        assert resolved.path == newest
        assert resolved.version == "0.10.0"


def test_resolve_ignores_creation_order():
    """Unordered creation (newest first) must not change the result."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        newest = _artifact_dir(root, "acme-pack", "0.10.0")
        _artifact_dir(root, "acme-pack", "0.2.0")
        _artifact_dir(root, "acme-pack", "0.8.0")

        resolved = DirectorySource(root).resolve("acme-pack")
        assert resolved.version == "0.10.0"
        assert resolved.path == newest


def test_resolve_picks_newest_on_lexicographic_trap():
    """0.2.0 vs 0.10.0: a naive string sort would pick 0.2.0."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _artifact_dir(root, "acme-pack", "0.2.0")
        newest = _artifact_dir(root, "acme-pack", "0.10.0")

        resolved = DirectorySource(root).resolve("acme-pack")
        assert resolved.path == newest
        assert resolved.version == "0.10.0"


def test_resolve_returns_none_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _artifact_dir(root, "acme-pack", "0.1.0")
        assert DirectorySource(root).resolve("other-pack") is None


def test_resolve_distinguishes_artifacts_by_name():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = _artifact_dir(root, "acme-pack", "0.1.0", mount="/opt/a")
        _artifact_dir(root, "other-pack", "0.9.0", mount="/opt/b")

        resolved = DirectorySource(root).resolve("acme-pack")
        assert resolved is not None
        assert resolved.path == a
        assert resolved.version == "0.1.0"
        assert resolved.mount == "/opt/a"
