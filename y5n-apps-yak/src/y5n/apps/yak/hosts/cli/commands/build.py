"""yak build [<target>] — build an artifact from the current project."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.workflow import build as build_workflow


def run(args, mgr) -> None:
    target = Path(args.target).resolve() if args.target else None
    build_workflow(output_dir=target)
