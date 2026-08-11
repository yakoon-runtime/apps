"""yak add <component> [<target>] — add a distribution or artifact to an installation."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_runtime_root
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    name = args.name

    root = _resolve_root(args)
    if root is None:
        ui.fail("No installation found — run 'yak install <environment>' first")
        return

    from y5n.apps.yak.installation.ask import TerminalStoreAsker

    ui.title(f'Adding "{name}"')
    try:
        result = mgr.add(
            name,
            root,
            asker=TerminalStoreAsker(),
            ui=ui,
            sources=_repositories(args),
            force=bool(
                getattr(args, "force", False) or getattr(args, "upgrade", False)
            ),
        )
        if result is None:
            ui.ok("Already installed")
            return
        ui.ok(f"Added {name}")
    except Exception as e:
        ui.fail(f"Failed: {e}")


def _resolve_root(args) -> Path | None:
    """The installation root: explicit target, else the current runtime root."""
    target = Path(getattr(args, "target", ".")).resolve()
    from y5n.apps.yak.environment.io import env_path

    if env_path(target).exists():
        return target
    return find_runtime_root()


def _repositories(args) -> list[str] | None:
    """Repositories: CLI --repository overrides, otherwise the context."""
    cli_repo = getattr(args, "repository", None)
    if cli_repo:
        return [cli_repo]

    from y5n.apps.yak.hosts.cli.cwd import Context

    ctx = Context.current()
    return list(ctx.repository_sources) if ctx else None
