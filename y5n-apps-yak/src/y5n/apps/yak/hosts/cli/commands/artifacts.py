"""yak artifacts — list and inspect available artifacts."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.resolver.install import _collect_roots
from y5n.apps.yak.resolver.artifact import _parse_manifest, DirectorySource


def run(args, mgr) -> None:
    action = getattr(args, "action", "list")
    if action == "list":
        _list_artifacts()
    elif action == "info":
        name = getattr(args, "name", "")
        if not name:
            print("Usage: yak artifacts info <name>")
            return
        _show_info(name)


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
