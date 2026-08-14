"""yak bootstrap — prepare a Yakoon repository for development.

Bootstrap materializes the same ``bootstrap.toml.install`` list as
``yak install``, but as *sources* instead of artifacts. Each
``github:<owner>/<repo>`` source maps to its local checkout
``<context-root>/<repo>`` — the directory name git clone creates. The
checkout must exist; acquiring missing repositories (git clone) is a
later concern. The result is a full development installation whose
components are editable installs from the local checkouts.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import Context, find_context_root
from y5n.apps.yak.hosts.cli.ui import TerminalUI
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def run(args, mgr) -> None:
    root = find_context_root()
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

    bootstrap_mgr = _bootstrap_manager(root)
    bootstrap_mgr.install(root, ui=ui, mode="source")
    print(f"  Yakoon ready for development at {root}")


def _bootstrap_manager(root: Path):
    """An InstallationManager whose sources are the local checkouts.

    ``github:<owner>/<repo>`` resolves to ``<root>/<repo>``; a missing
    checkout is a bootstrap error. Non-github sources pass through.
    """
    from y5n.apps.yak.hosts.cli.cwd import _load_context
    from y5n.apps.yak.installation.manager import InstallationManager

    ctx = _load_context(root)
    sources = [_to_local_checkout(spec, root) for spec in ctx.sources]
    bootstrap_ctx = Context(
        path=ctx.path,
        name=ctx.name,
        schema=ctx.schema,
        install=ctx.install,
        sources=sources,
        source_dirs=ctx.source_dirs,
    )
    roots = bootstrap_ctx.resolve_sources()
    repo = FileRepository(*roots)
    artifacts = DirectoryArtifactStore(*roots)
    return InstallationManager(repo, artifacts, context=bootstrap_ctx)


def _to_local_checkout(spec: str, root: Path) -> str:
    """Map a ``github:<owner>/<repo>`` source to its local checkout path.

    The repo name is the last path segment — the directory name ``git
    clone`` creates. There is no knowledge of any repository beyond what
    the source spec already states.
    """
    if not spec.startswith("github:"):
        return spec
    repo = spec.split(":", 1)[1].rsplit("/", 1)[-1]
    checkout = root / repo
    if not checkout.is_dir():
        raise RuntimeError(
            f"Source for '{repo}' not found: expected {checkout}\n"
            f"Clone it first (e.g. git clone {spec}) and run 'yak bootstrap' again."
        )
    return str(checkout)


def _check(root: Path) -> None:
    print("  Context     ✓" if root else "  Context     ✘")
    print(
        "  .venv       ✓"
        if (root / ".venv" / "bin" / "python").exists()
        else "  .venv       ✘"
    )
