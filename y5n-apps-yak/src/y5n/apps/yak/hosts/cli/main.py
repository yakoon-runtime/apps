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

  Build
    create pack            Scaffold a new pack
    create command         Add a command to the current pack
    build                  Build artifacts
    bootstrap              Prepare this repository for development

  Install
    install                Install an environment
    sync                   Sync environment with workspace

  Run
    runtime                Manage the runtime service
    shell                  Open the Yakoon shell
    web                    Manage the web service

  Tools
    status                 Show installation status
    doctor                 Check installation health
    logs                   Show logs
    resolve                Show resolved artifacts
    workspace create       Create a new workspace

Use 'yak <command> --help' for detailed options.
""")


def _build_manager() -> InstallationManager:
    from y5n.apps.yak.hosts.cli.cwd import find_context_root

    repo_root = Path(__file__).resolve().parents[8]
    packs = repo_root / "packs"
    runtime = repo_root / "runtime"
    artifact_dir = repo_root / "apps" / "y5n-apps-yak" / "artifacts"

    apps = repo_root / "apps"
    sdk = repo_root / "sdk" / "y5n-sdk-python"

    # ArtifactStore-Roots: Monorepo + Context (für standalone-Packs)
    store_roots = [packs, runtime, apps, sdk]
    ctx = find_context_root()
    if ctx is not None:
        store_roots.append(ctx)

    repo = FileRepository(packs, runtime, sdk, builtin_artifacts=artifact_dir)
    artifacts = DirectoryArtifactStore(*store_roots)
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
        print(f"Yakoon {VERSION}")
        return

    parser = build_parser()
    args = parser.parse_args()
    manager = _build_manager()
    args.func(args, manager)


if __name__ == "__main__":
    main()
