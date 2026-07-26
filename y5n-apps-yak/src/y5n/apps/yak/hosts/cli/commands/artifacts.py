"""yak artifacts [<name>] — list artifacts or show details."""

from __future__ import annotations

from y5n.apps.yak.resolver.install import _collect_roots
from y5n.apps.yak.resolver.artifact import _parse_manifest, DirectorySource


def run(args, mgr) -> None:
    name = getattr(args, "name", None)
    if name:
        _show_info(name)
    else:
        _list_artifacts()


def _list_artifacts() -> None:
    roots = _collect_roots(None)
    seen: set[str] = set()
    names: list[str] = []

    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            manifest = entry / "artifact.yml"
            if not manifest.exists():
                continue
            meta = _parse_manifest(manifest)
            name = meta.get("name", "")
            if name and name not in seen:
                seen.add(name)
                names.append(name)

    if names:
        print("  " + "\n  ".join(names))
    else:
        print("No artifacts found.")


def _show_info(name: str) -> None:
    from pathlib import Path
    roots = _collect_roots(None)

    for root in roots:
        source = DirectorySource(root)
        art = source.resolve(name)
        if art and art.path:
            manifest = art.path / "artifact.yml"
            if manifest.exists():
                print(manifest.read_text().strip())
                return

    print(f"Artifact not found: {name}")
