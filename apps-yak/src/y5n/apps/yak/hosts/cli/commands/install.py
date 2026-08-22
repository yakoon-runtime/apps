"""yak install <bundle> [--path <catalog>]... [--target <dir>].

The first argument is a bundle identity — the public install language.
``--path`` catalogs are preferred local sources stored per identity: a
component found there resolves through its ``location``, everything else
through its ``release`` — per component.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    root = Path(getattr(args, "target", ".")).resolve()
    identity = args.identity
    paths = getattr(args, "path", None)

    if getattr(args, "distribution", None):
        mgr.set_distribution(args.distribution)

    if not _is_bundle_or_component(mgr, identity, paths):
        ui.fail(
            f"'{identity}' is not a bundle — install identities are bundles "
            f"(e.g. 'runtime', 'system')."
        )
        return

    _ensure_context(root)

    ui.title(f'Installing "{identity}"')
    try:
        mgr.install(root, ui=ui, identity=identity, paths=paths)
        ui.ok(f"Installed {identity}")
    except Exception as e:
        ui.fail(f"Installation failed: {e}")


def _is_bundle_or_component(mgr, identity: str, paths) -> bool:
    """Whether the identity names a bundle (the public install language)."""
    if mgr._distribution() is not None:
        return mgr._distribution().resolve_bundle(
            identity
        ) is not None or mgr._distribution().has(identity)
    index = mgr._combined_index(paths)
    return index.resolve_bundle(identity) is not None


def _ensure_context(root: Path) -> None:
    """Create the context (sources → .yak/context.toml) if it is missing.

    The context carries the sources; without it no later command (add,
    update, shell) can resolve anything. Creating it is a no-op when the
    target already sits inside a context.
    """
    ctx_file = root / ".yak" / "context.toml"
    if ctx_file.exists():
        return
    from y5n.apps.yak.hosts.cli.commands import init_cmd

    init_cmd._init(root)
