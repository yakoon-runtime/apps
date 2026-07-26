"""yak update — update an installation."""

from __future__ import annotations

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

    # Artifact installation — re-install from cache
    if not mgr._repo.resolve_distribution(inst.distribution):
        ok = ui.task("Artifacts", lambda: install_artifact(
            inst.distribution, target_root=path, force=getattr(args, "force", False),
        ))
        if ok:
            print(f"  {path.name} updated")
        else:
            print("  Update failed — run 'yak build' first to refresh artifacts")
        return

    # Distribution installation
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

        with ui.step("Workspace"):
            mgr._materializer.materialize(path, dist.name, packs, mounts=mounts)

        with ui.step("Mounts"):
            for m in mounts:
                ui.detail(f"{m.pack} → {m.target}")

        with ui.step("Environment"):
            from datetime import UTC, datetime
            from y5n.apps.yak.installation.models import InstallationStatus

            now = datetime.now(UTC)
            inst.packs = packs
            inst.status = InstallationStatus.MATERIALIZED
            inst.updated = now
            mgr._write_state(inst)
            mgr._installer.install(inst, tools=tools, sdk_path=mgr._sdk_path)
            inst.status = InstallationStatus.CREATED
            inst.updated = datetime.now(UTC)
            mgr._write_state(inst)

        print(f"  {path.name} updated")

    except Exception as e:
        print(f"  Update failed: {e}")
