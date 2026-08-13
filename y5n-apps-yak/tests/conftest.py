"""Shared helpers for the source-catalog model (ADR-20)."""

from __future__ import annotations

from pathlib import Path


def make_source(
    path: Path,
    components: dict | None = None,
    environments: dict | None = None,
    sub_sources: list[str] | None = None,
) -> Path:
    """Create a source directory with a declared catalog.yml."""
    path.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if sub_sources:
        lines.append("sources:")
        for sub in sub_sources:
            lines.append(f"  - {sub!r}")
    components = components or {}
    if components:
        lines.append("components:")
        for name, entry in components.items():
            lines.append(f"  {name}:")
            lines.append(f"    version: {entry.get('version', '0.1')!r}")
            lines.append(f"    location: {entry['location']!r}")
    else:
        lines.append("components: {}")
    if environments:
        lines.append("environments:")
        for name, location in environments.items():
            lines.append(f"  {name}: {location!r}")
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


def environment(source: Path, name: str, components: list[str]) -> Path:
    """An environment manifest resource inside a source."""
    env_dir = source / "environments"
    env_dir.mkdir(parents=True, exist_ok=True)
    path = env_dir / f"{name}.yml"
    path.write_text(
        "name: " + name + "\ncomponents:\n" + "".join(f"  - {c}\n" for c in components)
    )
    return path
