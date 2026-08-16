"""yak deploy <bundle|name> [--to <repository>] — deploy published artifacts.

A bundle identity expands to its components; each is deployed to the
context's distribution repository (``dists``) — the single home of built
software. ``--to`` overrides the target for a component that does not
belong to the distribution yet.
"""

from __future__ import annotations

from y5n.apps.yak.publisher.publish import deploy_artifact


def run(args, mgr) -> None:
    names = mgr._bundle_members(args.name)
    is_bundle = mgr._index().resolve_bundle(args.name) is not None
    if is_bundle and getattr(args, "to", None):
        print(
            "A bundle deploys to the distribution repository; "
            "--to is only for a single component."
        )
        return

    override = getattr(args, "to", None)
    target = override if override is not None else mgr._distribution_spec()
    if target is None:
        print("No distribution repository configured.")
        print("Set 'distribution' in .yak/context.toml or use --to <repository>.")
        return

    for name in names:
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
