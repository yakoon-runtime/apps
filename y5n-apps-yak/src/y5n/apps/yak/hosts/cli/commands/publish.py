"""yak publish <name> — publish an artifact."""

from __future__ import annotations

from y5n.apps.yak.publisher.publish import publish_artifact


def run(args, mgr) -> None:
    name = args.name
    target = getattr(args, "target", None)

    result = publish_artifact(name, target=target)
    if result is None:
        print(f"  Artifact '{name}' not found in context")
        print("  Run 'yak build <source>' first to build it.")
        return

    if result is True:
        print(f"  Published {name} to {target}")
        print(f"  Install with: yak install {name} --source {target}")
    elif isinstance(result, Path):
        print(f"  Published {name} to {result}")
        print(f"  Install anywhere with: yak install {name}")
