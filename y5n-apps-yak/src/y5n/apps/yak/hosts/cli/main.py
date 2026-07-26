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
    init          [dir]     Create a Yak context

  Development
    create pack <name>      Scaffold a new pack (container)
    create command <name>   Add a command to the current pack
    build         [src]     Build artifacts into the current context
    bootstrap               Prepare this repository for development
    workspace create <n>    Create a new workspace
    resolve  <name>         Show resolved artifacts

  Management
    install       [name]    Install an environment or list available
    update                  Update an installation
    status                  Show installation status
    doctor                  Check installation health
    logs          [name]    Show logs for the current context

  Services
    runtime <act> [dir]     Manage the runtime service
    web     <act> [dir]     Manage the web service
    shell                   Open the Yakoon shell

Use 'yak <command> --help' for detailed options.
""")


def _build_manager() -> InstallationManager:
    repo_root = Path(__file__).resolve().parents[8]
    packs = repo_root / "packs"
    runtime = repo_root / "runtime"
    artifact_dir = repo_root / "apps" / "y5n-apps-yak" / "artifacts"

    apps = repo_root / "apps"
    sdk = repo_root / "sdk" / "y5n-sdk-python"
    repo = FileRepository(packs, runtime, sdk, builtin_artifacts=artifact_dir)
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
