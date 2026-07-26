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
    from pathlib import Path

    seen: set[str] = set()
    names: list[str] = []

    # Bundled artifacts (dev.yml, desktop.yml, ...)
    bundle_dir = Path(__file__).resolve().parents[7] / "artifacts"
    if bundle_dir.is_dir():
        for f in sorted(bundle_dir.iterdir()):
            if f.suffix == ".yml":
                meta = _parse_manifest(f)
                if meta.get("kind") == "meta":
                    name = meta.get("name", "")
                    if name and name not in seen:
                        seen.add(name)
                        names.append(name)

    # Cached artifacts
    for root in _collect_roots(None):
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            manifest = entry / "artifact.yml"
            if not manifest.exists():
                continue
            meta = _parse_manifest(manifest)
            if meta.get("kind") != "meta":
                continue
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
