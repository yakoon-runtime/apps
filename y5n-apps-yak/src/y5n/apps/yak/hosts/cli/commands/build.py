"""yak build [<source-or-name>] — build an artifact from a source or pack name."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.workflow import build as build_workflow
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI()

    def _build():
        raw = getattr(args, "source", None)
        if not raw:
            print("Error: no source given.")
            print("Usage: yak build <source-or-name>  (e.g. yak build system)")
            return False

        source = Path(raw).resolve()
        if not source.is_dir():
            pack_dir = mgr._repo.resolve_pack_dir(raw)
            if pack_dir is None:
                print(f"Unknown pack: {raw}")
                return False
            source = pack_dir

        return build_workflow(project_dir=source)

    ok = ui.task("Build", _build)
    if not ok:
        ui.fail("Build failed")
