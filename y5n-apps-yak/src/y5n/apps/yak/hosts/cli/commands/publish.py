"""yak publish <name> — publish an artifact."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.publisher.publish import publish_artifact


def run(args, mgr) -> None:
    name = args.name
    repository = getattr(args, "repository", None)
    release = getattr(args, "release", False)
    if release:
        repository = f"{repository}?release" if repository else None

    result = publish_artifact(name, target=repository)
    if result is None:
        print(f"  Artifact '{name}' not found in context")
        print("  Run 'yak build <source>' first to build it.")
        return

    if result is True:
        print(f"  Published {name} to {repository}")
        print(f"  Install with: yak install {name} --repository {repository}")
    else:
        print(f"  Published {name} to {result}")
        print(f"  Install anywhere with: yak install {name}")
