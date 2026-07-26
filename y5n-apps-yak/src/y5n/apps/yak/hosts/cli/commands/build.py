"""yak build — build an artifact from the current project."""

from __future__ import annotations

from y5n.apps.yak.builder.workflow import build as build_workflow


def run(args, mgr) -> None:
    build_workflow()
