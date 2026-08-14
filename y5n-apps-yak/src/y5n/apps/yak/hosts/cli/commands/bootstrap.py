"""yak bootstrap — prepare a Yakoon repository for development.

Bootstrapping installs the platform from the context's sources into the
current working tree. It is the same installation model as
``yak install`` (released artifacts); the sources may be local checkout
paths (the developer's own catalogs) or remote sources — the resolver
does not care. The result is a full installation: ``.yak/`` with
environment.yml, state.toml, deployment.yml and components/.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    root = _context_root()
    if root is None:
        print("Error: no Yak context here — run 'yak init' first")
        return

    if getattr(args, "check", False):
        _check(root)
        return

    if getattr(args, "force", False):
        venv = root / ".venv"
        if venv.exists():
            import shutil

            shutil.rmtree(venv)

    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    ui.title("Bootstrapping Yakoon")
    mgr.install(root, ui=ui)
    print(f"  Yakoon ready for development at {root}")


def _check(root: Path) -> None:
    print("  Context     ✓" if root else "  Context     ✘")
    print(
        "  .venv       ✓"
        if (root / ".venv" / "bin" / "python").exists()
        else "  .venv       ✘"
    )


def _context_root() -> Path | None:
    from y5n.apps.yak.hosts.cli.cwd import find_context_root

    return find_context_root()
