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


def main() -> int:
    """Run the CLI.

    The command contract: a command returns normally on success and
    raises SystemExit for a reported failure; any other exception is an
    unexpected error and exits non-zero with a message. The process exit
    code therefore reflects the command's outcome.
    """
    if len(sys.argv) <= 1:
        _show_banner()
        return 0
    if sys.argv[1] in ("-V", "--version"):
        print(f"Yakoon {VERSION}")
        return 0

    parser = build_parser()
    args = parser.parse_args()
    manager = _build_manager()
    try:
        args.func(args, manager)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
