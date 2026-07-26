"""yak artifacts — list available artifacts."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.resolver.install import _collect_roots
from y5n.apps.yak.resolver.artifact import _parse_manifest


def run(args, mgr) -> None:
    roots = _collect_roots(None)
    if not roots:
        print("No artifact sources found.")
        return

    seen: set[str] = set()
    categories: dict[str, list[tuple[str, str]]] = {}

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
            if not name or name in seen:
                continue
            seen.add(name)
            kind = meta.get("kind", "package")
            desc = meta.get("description", "")

            # Simple category mapping
            if kind == "meta":
                cat = "Meta"
            elif name.startswith("y5n-apps-"):
                cat = "Apps"
            elif name.startswith("y5n-packs-"):
                cat = "Packs"
            elif name.startswith("y5n-sdk-"):
                cat = "SDK"
            elif name.startswith("y5n-runtime-"):
                cat = "Runtime"
            else:
                cat = "Other"

            categories.setdefault(cat, []).append((name, desc))

    for cat in ["Meta", "Apps", "Runtime", "SDK", "Packs", "Other"]:
        items = categories.get(cat)
        if not items:
            continue
        print(f"\n  {cat}")
        for name, desc in items:
            desc_str = f"  — {desc}" if desc else ""
            print(f"    {name}{desc_str}")
