"""yak update — reconcile environment: install wheels + sync env + materialize workspace."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.distribution.models import PackName
from y5n.apps.yak.environment.io import load, save
from y5n.apps.yak.environment.sync import add_mount
from y5n.apps.yak.hosts.cli.cwd import find_installation_path
from y5n.apps.yak.hosts.cli.ui import TerminalUI
from y5n.apps.yak.resolver.install import install_artifact


def run(args, mgr) -> None:
    path = find_installation_path()
    if path is None:
        print("Not inside a Yak installation.")
        print("Run 'yak install' first or cd into one.")
        return

    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    print(f'\n  Updating "{path.name}"\n')

    inst = mgr.load(path)
    if inst is None:
        ui.fail("Installation not found")
        return

    # 1. Install wheels
    if not mgr._repo.resolve_distribution(inst.distribution):
        _install_artifact(path, args, ui, inst, mgr)
    else:
        _install_distribution(path, mgr, ui, inst)

    # 2. Sync environment: add mounts for all discovered packs
    env = load(path)
    if env is None:
        print("  Warning: no .yak/environment.yml found")
    else:
        discovered = _discover_packs(path)
        for pack in discovered:
            add_mount(env, pack)
        save(env, path)
        print(f"  Environment synced ({len(env.mounts)} mounts)")

    # 3. Materialize workspace from environment
    if env:
        _materialize_from_env(path, mgr, env)


def _discover_packs(context_root: Path) -> list[PackName]:
    """Scan context root for directories with pack.toml."""
    from y5n.apps.yak.distribution.models import PackName

    packs: list[PackName] = []

    # Known artifact roots
    for root in [context_root]:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "pack.toml").exists():
                packs.append(PackName(child.name))

    return packs


def _install_artifact(path: Path, args, ui, inst, mgr) -> None:
    ok = ui.task(
        "Artifacts",
        lambda: install_artifact(
            inst.distribution,
            target_root=path,
            force=getattr(args, "force", False),
        ),
    )
    if ok:
        from y5n.apps.yak.hosts.cli.commands.install import (
            _materialize_dev_workspace,
        )

        _materialize_dev_workspace(inst.distribution, path, mgr)
        print("  Artifacts installed")
    else:
        print("  Update failed — run 'yak build' first to refresh artifacts")


def _install_distribution(path: Path, mgr, ui, inst) -> None:
    from datetime import UTC, datetime

    from y5n.apps.yak.installation.models import InstallationStatus

    try:
        ui.title(f'Updating "{path.name}"')

        with ui.step("Distribution"):
            dist = mgr._repo.resolve_distribution(inst.distribution)
            ui.detail(inst.distribution)

        from y5n.apps.yak.resolver.resolver import Resolver

        resolver = Resolver(lambda n: mgr._repo.resolve_distribution(n))
        packs, mounts, tools = resolver.resolve(dist)

        with ui.step("Packs"):
            ui.detail(", ".join(packs))

        with ui.step("Mounts"):
            for m in mounts:
                ui.detail(f"{m.pack} → {m.target}")

        with ui.step("Environment"):
            now = datetime.now(UTC)
            inst.packs = packs
            inst.status = InstallationStatus.MATERIALIZED
            inst.updated = now
            mgr._write_state(inst)
            mgr._installer.install(inst, tools=tools, sdk_path=mgr._sdk_path)
            inst.status = InstallationStatus.CREATED
            inst.updated = datetime.now(UTC)
            mgr._write_state(inst)

    except Exception as e:
        print(f"  Update failed: {e}")


def _materialize_from_env(path: Path, mgr, env) -> None:
    """Materialize workspace from environment.yml mounts."""
    from y5n.apps.yak.distribution.models import Mount, PackName
    from y5n.apps.yak.workspace.materializer import Materializer

    materializer = Materializer(mgr._artifacts)
    mounts = [Mount(pack=PackName(m.pack), target=m.target) for m in env.mounts]
    packs = [PackName(m.pack) for m in env.mounts]
    ws = materializer.materialize(path, env.name, packs, mounts=mounts)
    print(f"  Workspace materialized at {ws.path / 'structure'}")
