from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path
from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    path = Path(args.path).resolve() if args.path else find_installation_path()
    if path is None:
        print("No installation specified. Use --path <dir> or cd into one.")
        return

    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    ui.title(f'Updating "{path.name}"')

    try:
        inst = mgr.load(path)
        if inst is None:
            raise RuntimeError("Installation not found")

        with ui.step("Distribution"):
            dist = mgr._repo.resolve_distribution(inst.distribution)
            ui.detail(inst.distribution)

        with ui.step("Packs"):
            packs, mounts, tools = mgr._resolver.resolve(dist)

            # Add extra packs from --add
            if hasattr(args, "add") and args.add:
                for extra in args.add:
                    extra_dist = mgr._repo.resolve_distribution(extra)
                    if extra_dist is None:
                        raise ValueError(f"Unknown pack: {extra}")
                    extra_packs, extra_mounts, extra_tools = mgr._resolver.resolve(
                        extra_dist
                    )
                    new_packs = [p for p in extra_packs if p not in packs]
                    packs.extend(new_packs)
                    mounts.extend(extra_mounts)
                    tools.extend(extra_tools)
                    ui.detail(f"+ {extra}")

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

        ui.ok(f"{path.name} updated")

    except Exception as e:
        ui.fail(f"Update failed: {e}")
