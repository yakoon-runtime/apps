"""yak publish <bundle|name> — publish artifacts to the system-global store.

A bundle identity expands to its components; each is published
individually. Remote distribution is handled by ``yak deploy``.
"""

from __future__ import annotations

from y5n.apps.yak.publisher.publish import publish_local


def run(args, mgr) -> None:
    names = mgr._bundle_members(args.name)
    failed = False
    for name in names:
        result = publish_local(name)
        if result is None:
            print(f"  Artifact '{name}' not found in context")
            print("  Run 'yak build <bundle|path>' first to build it.")
            failed = True
            continue
        print(f"  Published {name} to {result}")
    print(f"  Install anywhere with: yak install {args.name}")
    if failed:
        raise SystemExit(1)
