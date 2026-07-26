"""yak build [<source>] — build an artifact from the given source."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.workflow import build as build_workflow
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI()

    def _build():
        source = Path(args.source).resolve() if args.source else None
        return build_workflow(project_dir=source)

    ok = ui.task("Build", _build)
    if not ok:
        ui.fail("Build failed")
