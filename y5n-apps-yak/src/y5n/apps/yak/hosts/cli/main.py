from __future__ import annotations

import sys
from pathlib import Path

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
    from y5n.apps.yak.hosts.cli.cwd import Context, default_sources

    ctx = Context.current()
    roots = ctx.resolve_sources() if ctx else default_sources()

    artifact_dir = (
        Path(__file__).resolve().parents[8] / "apps" / "y5n-apps-yak" / "artifacts"
    )

    # Old monorepo-specific paths for backwards compat
    repo_root = Path(__file__).resolve().parents[8]

    repo = FileRepository(*roots, builtin_artifacts=artifact_dir)
    artifacts = DirectoryArtifactStore(*roots)
    return InstallationManager(
        repo,
        artifacts,
        sdk_path=repo_root / "sdk" / "y5n-sdk-python",
        apps_root=repo_root / "apps",
        runtime_root=repo_root / "runtime",
    )


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
