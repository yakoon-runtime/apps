"""yak publish <name> — publish an artifact to ~/.yak/artifacts/."""

from __future__ import annotations

from y5n.apps.yak.publisher.publish import publish_artifact


def run(args, mgr) -> None:
    name = args.name

    dest = publish_artifact(name)
    if dest is None:
        print(f"  Artifact '{name}' not found in context")
        print("  Run 'yak build <source>' first to build it.")
        return

    print(f"  Published {name} to {dest}")
    print(f"  Install anywhere with: yak install {name}")
