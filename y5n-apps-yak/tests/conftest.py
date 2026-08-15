"""Shared helpers for the source-catalog model (ADR-20)."""

from __future__ import annotations

from pathlib import Path


def make_source(
    path: Path,
    components: dict | None = None,
    bundles: dict | None = None,
) -> Path:
    """Create a source directory with a declared catalog.yml."""
    path.mkdir(parents=True, exist_ok=True)
    components = components or {}
    lines = ["components:"]
    if components:
        for name, entry in components.items():
            lines.append(f"  {name}:")
            lines.append(f"    version: {entry.get('version', '0.1')!r}")
            lines.append(f"    location: {entry['location']!r}")
            release = entry.get("release")
            if release is not None:
                lines.append(f"    release: {release!r}")
    else:
        lines.append("  {}")
    if bundles:
        lines.append("bundles:")
        for name, members in bundles.items():
            lines.append(f"  {name}:")
            for member in members:
                lines.append(f"    - {member!r}")
    (path / "catalog.yml").write_text("\n".join(lines) + "\n")
    return path


def source_pack(path: Path, name: str, mount: str) -> Path:
    """A source-pack component: pack.toml + structure."""
    (path / "structure").mkdir(parents=True, exist_ok=True)
    (path / "structure" / "payload.txt").write_text(f"{name}-source")
    (path / "pack.toml").write_text(
        f'name = "{name}"\nversion = "0.1"\nmount = "{mount}"\n'
    )
    return path


def artifact(
    path: Path,
    name: str,
    mount: str,
    content: str = "data",
    fingerprint: str | None = None,
) -> Path:
    """An artifact component: artifact.yml + structure."""
    (path / "structure").mkdir(parents=True, exist_ok=True)
    (path / "structure" / "payload.txt").write_text(content)
    (path / "artifact.yml").write_text(
        "name: " + name + "\n"
        "version: 0.1.0\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        "mount: " + mount + "\n"
        "fingerprint: sha256:" + (fingerprint or name) + "\n"
    )
    return path
