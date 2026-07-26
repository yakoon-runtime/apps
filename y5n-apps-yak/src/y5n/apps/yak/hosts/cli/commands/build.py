"""yak build [<target>] — build an artifact from the current project."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.workflow import build as build_workflow
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI()

    def _build():
        target = Path(args.target).resolve() if args.target else None
        return build_workflow(output_dir=target)

    ok = ui.task("Build", _build)
    if not ok:
        ui.fail("Build failed")
