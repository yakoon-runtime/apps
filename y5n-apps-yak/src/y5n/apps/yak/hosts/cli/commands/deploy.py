"""yak deploy <bundle|name> [--to <source>] — deploy published artifacts.

A bundle identity expands to its components; each is deployed to the
source whose catalog offers it — ``deploy`` and resolution share one
truth, the index already knows where each component belongs. ``--to`` is
only valid for a single component that exists in no catalog (a new
component being deployed into its source for the first time).
"""

from __future__ import annotations

from y5n.apps.yak.publisher.publish import deploy_artifact


def run(args, mgr) -> None:
    names = mgr._bundle_members(args.name)
    is_bundle = mgr._index().resolve_bundle(args.name) is not None
    if is_bundle and getattr(args, "to", None):
        print(
            "A bundle deploys to its members' home catalogs; "
            "--to is only for a single component."
        )
        return

    override = getattr(args, "to", None)
    for name in names:
        target = override if override is not None else _catalog_source(mgr, name)
        if target is None:
            print(f"Component '{name}' is in no catalog.")
            print(f"Deploy it explicitly: yak deploy {name} --to <source>")
            continue

        try:
            result = deploy_artifact(name, target)
        except RuntimeError as exc:
            print(str(exc))
            continue
        if result is None:
            print(f"Artifact '{name}' is not published.")
            print("Run 'yak publish <name>' first.")
            continue
        if not result:
            print(f"Deploy to '{target}' failed.")
            continue
        print(f"Deployed {name} to {target}")


def _catalog_source(mgr, name: str) -> str | None:
    """The source spec whose catalog offers the component (its home)."""
    hit = mgr._index().resolve(name)
    if hit is None:
        return None
    catalog, _ref = hit
    return catalog.spec
