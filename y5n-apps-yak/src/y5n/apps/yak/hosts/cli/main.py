from __future__ import annotations

import sys
from pathlib import Path

from y5n.apps.yak.hosts.cli.parser import build_parser
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository

VERSION = "0.1.0"


def _show_banner() -> None:
    print(f"""Yakoon Platform Manager {VERSION}

Usage:
    yak <command> [options]

  Getting started
    init          [dir]     Create a Yak context in current or given directory

  Development
    build                   Build artifacts from the current project
    bootstrap               Prepare this repository for development
    workspace create <name> Create a new workspace
    resolve  <name>         Show resolved artifacts

  Management
    install <name>          Install a distribution
    update                  Update an installation
    status                  Show installation status
    doctor                  Check installation health
    artifacts list          List available artifacts
    artifacts info <name>   Show artifact details
    logs         [name]     Show logs for the current context

  Services
    runtime <act>           Manage the runtime service
    web     <act>           Manage the web service
    shell                   Open the Yakoon shell

Use 'yak <command> --help' for detailed options.
""")


def _build_manager() -> InstallationManager:
    repo_root = Path(__file__).resolve().parents[8]
    packs = repo_root / "packs"
    runtime = repo_root / "runtime"
    dists = repo_root / "apps" / "y5n-apps-yak" / "dists"

    apps = repo_root / "apps"
    sdk = repo_root / "sdk" / "y5n-sdk-python"
    repo = FileRepository(packs, runtime, sdk, builtin_dists=dists)
    artifacts = DirectoryArtifactStore(packs, runtime, apps, sdk)
    mgr = InstallationManager(repo, artifacts)
    mgr._sdk_path = sdk
    mgr._installer._apps_root = apps
    mgr._installer._runtime_root = runtime
    return mgr


def main() -> None:
    if len(sys.argv) <= 1:
        _show_banner()
        return
    if sys.argv[1] in ("-V", "--version"):
        print(f"Yakoon Platform Manager {VERSION}")
        return

    parser = build_parser()
    args = parser.parse_args()
    manager = _build_manager()
    args.func(args, manager)


if __name__ == "__main__":
    main()
