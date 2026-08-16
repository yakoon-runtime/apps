from __future__ import annotations

import sys

from y5n.apps.yak.hosts.cli.parser import build_parser
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository

try:
    from importlib.metadata import version as _pkg_version

    VERSION = _pkg_version("y5n-apps-yak")
except Exception:
    VERSION = "0.1.0"


def _show_banner() -> None:
    from y5n.apps.yak.hosts.cli.usage import USAGE

    print(f"Yakoon {VERSION}\n\n{USAGE}")


def _build_manager() -> InstallationManager:
    from y5n.apps.yak.hosts.cli.cwd import Context

    ctx = Context.current()
    # Component sources come from the context only — no hidden monorepo
    # fallback. Without a context there are no source directories; add
    # then resolves components from the local artifact store and the
    # configured repositories.
    roots = ctx.resolve_sources() if ctx is not None else []

    repo = FileRepository(*roots)
    artifacts = DirectoryArtifactStore(*roots)
    return InstallationManager(repo, artifacts, context=ctx)


def main() -> None:
    if len(sys.argv) <= 1:
        _show_banner()
        return
    if sys.argv[1] in ("-V", "--version"):
        print(f"Yakoon {VERSION}")
        return

    parser = build_parser()
    args = parser.parse_args()
    manager = _build_manager()
    args.func(args, manager)


if __name__ == "__main__":
    main()
