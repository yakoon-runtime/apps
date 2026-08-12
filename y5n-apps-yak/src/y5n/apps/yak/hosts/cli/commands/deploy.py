"""yak deploy <name> --to <repository> — make a published artifact available remotely."""

from __future__ import annotations


def run(args, mgr) -> None:
    from y5n.apps.yak.publisher.publish import deploy_artifact

    try:
        result = deploy_artifact(args.name, args.to)
    except RuntimeError as exc:
        print(str(exc))
        return
    if result is None:
        print(f"Artifact '{args.name}' is not published.")
        print("Run 'yak publish <name>' first.")
        return
    if not result:
        print(f"Deploy to '{args.to}' failed.")
        return
    print(f"Deployed {args.name} to {args.to}")
