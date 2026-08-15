"""yak build <bundle|path> — build artifacts from source.

The public lifecycle identity is a bundle: ``runtime`` expands to its
components and each is built from its catalog source. A path is the
developer escape hatch for a single project
(``yak build ./runtime/packages/y5n-runtime-engine``).
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.builder.workflow import build as build_workflow
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI()
    raw = getattr(args, "source", None)
    if not raw:
        ui.fail("No source given — usage: yak build <bundle|path>")
        return

    targets = _resolve_targets(raw, mgr)
    if targets is None:
        ui.fail(f"Unknown identity: {raw} — usage: yak build <bundle|path>")
        return

    ok = True
    for target in targets:
        ok = build_workflow(project_dir=target) and ok
    if not ok:
        ui.fail("Build failed")


def _resolve_targets(raw: str, mgr) -> list[Path] | None:
    """The project dirs to build: a path, a bundle's members, or a pack.

    A path (leading ``.``, ``/``, ``~`` or containing ``/``) is built as
    one project — the developer escape hatch. A bundle identity expands
    to its members, each resolved through the catalog index. A plain pack
    name falls back to the existing folder == name lookup.
    """
    if _is_path_like(raw):
        source = Path(raw).expanduser().resolve()
        return [source] if source.is_dir() else None

    bundle = mgr._index().resolve_bundle(raw)
    if bundle is not None:
        dirs: list[Path] = []
        for name in bundle[1]:
            hit = mgr._index().resolve(name)
            if hit is None:
                return None
            catalog, ref = hit
            member = mgr._materialize_location(catalog, ref.location)
            if member is None:
                return None
            dirs.append(member)
        return dirs

    pack_dir = mgr._repo.resolve_pack_dir(raw)
    if pack_dir is not None:
        return [pack_dir]
    return None


def _is_path_like(raw: str) -> bool:
    """Whether the target names a filesystem path rather than an identity."""
    return raw.startswith((".", "/", "~")) or "/" in raw
