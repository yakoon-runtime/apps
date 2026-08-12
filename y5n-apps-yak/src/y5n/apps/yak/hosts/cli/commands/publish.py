"""yak publish <name> — publish an artifact to the system-global store.

Remote distribution is handled by ``yak deploy``.
"""

from __future__ import annotations

from y5n.apps.yak.publisher.publish import publish_local


def run(args, mgr) -> None:
    result = publish_local(args.name)
    if result is None:
        print(f"  Artifact '{args.name}' not found in context")
        print("  Run 'yak build <source>' first to build it.")
        return
    print(f"  Published {args.name} to {result}")
    print(f"  Install anywhere with: yak install {args.name}")
