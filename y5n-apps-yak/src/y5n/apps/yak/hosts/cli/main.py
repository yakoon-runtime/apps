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
    print(f"""Yakoon {VERSION}

Usage:
    yak <command> [options]

  Getting started
    init                   Create a Yak context

  Development
    create pack            Create a new pack
    create command         Add a command to the current pack
    bootstrap              Prepare this repository for development

  Packaging
    build                  Build artifacts
    publish                Publish an artifact

  Environment
    install                Install a pack
    sync                   Sync workspace with environment

  Run
    shell                  Open the Yakoon shell
    runtime                Manage the runtime service
    web                    Manage the web service

  Tools
    status                 Show installation status
    mount                  Manage workspace mounts
    logs                   Show logs
    doctor                 Check installation health

Use 'yak <command> --help' for detailed options.
""")


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
    mgr = InstallationManager(repo, artifacts)
    mgr._sdk_path = repo_root / "sdk" / "y5n-sdk-python"
    mgr._installer._apps_root = repo_root / "apps"
    mgr._installer._runtime_root = repo_root / "runtime"
    return mgr


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
