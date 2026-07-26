"""yak update — reconcile environment: install wheels + sync env + materialize workspace."""

from __future__ import annotations

from pathlib import Path

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

    # 2. Sync environment: add mounts for all installed packs
    env = load(path)
    if env is None:
        print("  Warning: no .yak/environment.yml found")
    else:
        for pack in inst.packs:
            add_mount(env, pack)
        save(env, path)
        print(f"  Environment synced ({len(env.mounts)} mounts)")

    # 3. Materialize workspace from environment
    if env:
        _materialize_from_env(path, mgr, env)


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

    ws_path = path / env.workspace_path
    ws_path.mkdir(parents=True, exist_ok=True)
    structure = ws_path / "structure"
    structure.mkdir(exist_ok=True)

    for mount in env.mounts:
        artifact = mgr._artifacts.get_artifact(mount.pack)
        if artifact is None:
            continue
        pack_struct = artifact / "structure"
        if not pack_struct.is_dir():
            continue

        if mount.target == "/":
            for child in sorted(pack_struct.iterdir()):
                dst = structure / child.name
                if not dst.exists():
                    dst.symlink_to(child.resolve(), target_is_directory=child.is_dir())
        else:
            target = structure / mount.target.strip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.symlink_to(pack_struct, target_is_directory=True)

    print(f"  Workspace materialized at {structure}")
