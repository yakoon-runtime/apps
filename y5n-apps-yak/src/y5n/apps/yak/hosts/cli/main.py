from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.parser import build_parser
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _build_manager() -> InstallationManager:
    repo_root = Path(__file__).resolve().parents[5]
    repos = repo_root / "repos"
    runtime = repo_root / "runtime"
    dists = repo_root / "yak" / "dists"

    apps = repo_root / "apps"
    sdk = repo_root / "sdk" / "python"
    repo = FileRepository(repos, runtime, sdk, builtin_dists=dists)
    artifacts = DirectoryArtifactStore(repos, runtime, apps, sdk)
    mgr = InstallationManager(repo, artifacts)
    mgr._sdk_path = sdk
    mgr._installer._apps_root = apps
    mgr._sdk_path = sdk
    return mgr


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    manager = _build_manager()
    args.func(args, manager)


if __name__ == "__main__":
    main()
