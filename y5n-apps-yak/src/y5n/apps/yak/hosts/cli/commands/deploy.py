"""yak deploy <name> [--to <source>] — deploy a published artifact.

The target is the source whose catalog offers the component: ``deploy``
and resolution share one truth — the index already knows where the
component belongs. ``--to`` is only needed for a component that exists
in no catalog (a new component being deployed into its source for the
first time).
"""

from __future__ import annotations


def run(args, mgr) -> None:
    from y5n.apps.yak.publisher.publish import deploy_artifact

    target = getattr(args, "to", None)
    if target is None:
        target = _catalog_source(mgr, args.name)
        if target is None:
            print(f"Component '{args.name}' is in no catalog.")
            print(f"Deploy it explicitly: yak deploy {args.name} --to <source>")
            return

    try:
        result = deploy_artifact(args.name, target)
    except RuntimeError as exc:
        print(str(exc))
        return
    if result is None:
        print(f"Artifact '{args.name}' is not published.")
        print("Run 'yak publish <name>' first.")
        return
    if not result:
        print(f"Deploy to '{target}' failed.")
        return
    print(f"Deployed {args.name} to {target}")


def _catalog_source(mgr, name: str) -> str | None:
    """The source spec whose catalog offers the component (its home)."""
    hit = mgr._index().resolve(name)
    if hit is None:
        return None
    catalog, _ref = hit
    return catalog.spec
