"""yak bootstrap — prepare a Yakoon repository for development."""

from __future__ import annotations

from y5n.apps.yak.bootstrap.workflow import bootstrap


def run(args, mgr) -> None:
    force = getattr(args, "force", False)
    check = getattr(args, "check", False)
    bootstrap(force=force, check=check)
