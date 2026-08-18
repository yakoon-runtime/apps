"""yak deploy <bundle|name> [--to <repository>] — deploy published artifacts.

A bundle identity expands to its components; each is deployed to its own
distribution, which defaults to the source of the catalog that discovered
it (ADR-23 Step 3) — a component of ``github:owner/repo`` deploys to
``github:owner/repo``. ``--to`` overrides the target for a component that
does not belong to it yet (a single component, never a bundle).
"""

from __future__ import annotations

from y5n.apps.yak.publisher.publish import deploy_artifact


def run(args, mgr) -> None:
    names = mgr._bundle_members(args.name)
    is_bundle = mgr._index().resolve_bundle(args.name) is not None
    if is_bundle and getattr(args, "to", None):
        print(
            "A bundle deploys each member to its own distribution; "
            "--to is only for a single component."
        )
        return

    override = getattr(args, "to", None)
    for name in names:
        target = override
        if target is None:
            hit = mgr._index().resolve(name)
            if hit is None:
                print(f"Component '{name}' is not discoverable from any source.")
                continue
            catalog, _ref = hit
            if catalog.base is not None:
                print(
                    f"Component '{name}' has a local source ({catalog.spec}); "
                    "use --to <repository> to deploy it."
                )
                continue
            target = catalog.spec
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