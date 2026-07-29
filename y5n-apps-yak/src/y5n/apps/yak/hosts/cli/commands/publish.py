"""yak publish <name> — publish an artifact."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.publisher.publish import publish_artifact


def run(args, mgr) -> None:
    name = args.name
    repository = getattr(args, "repository", None)
    release = getattr(args, "release", False)
    target = repository

    result = publish_artifact(name, target=target, release=release)
    if result is None:
        print(f"  Artifact '{name}' not found in context")
        print("  Run 'yak build <source>' first to build it.")
        return

    if result is True:
        repo_display = repository or "~/.yak/artifacts/"
        print(f"  Published {name} to {repo_display}")
        print(f"  Install with: yak install {name} --repository {repository}")
    else:
        print(f"  Published {name} to {result}")
        print(f"  Install anywhere with: yak install {name}")
