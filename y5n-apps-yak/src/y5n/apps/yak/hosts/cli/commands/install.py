"""yak install <artifact> [<target>] — install an artifact or distribution."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path
from y5n.apps.yak.hosts.cli.ui import TerminalUI
from y5n.apps.yak.resolver.install import install_artifact, write_installation_marker


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))

    if _is_distribution(args.artifact, mgr):
        _distribution_install(args, mgr, ui)
    else:
        _artifact_install(args, ui)


def _artifact_install(args, ui) -> None:
    target = Path(args.target).resolve()
    ok = install_artifact(args.artifact, target_root=target)
    if ok:
        write_installation_marker(args.artifact, target)
        ui.ok(f"Installed {args.artifact} at {target}")
    else:
        ui.fail(f"Unknown target: {args.artifact}")


def _distribution_install(args, mgr, ui) -> None:
    artifact = args.artifact
    target = Path(args.target).resolve()
    root = target / artifact

    existing = root if (root / ".yak" / "state.toml").exists() else None

    if existing is not None:
        _add_to_existing(args, mgr, ui, existing)
    else:
        _create_new(args, mgr, ui, artifact, root)


def _is_distribution(name: str, mgr) -> bool:
    return mgr._repo.resolve_distribution(name) is not None


def _create_new(args, mgr, ui, name, root):
    ui.title(f'Installing "{name}"')

    try:
        with ui.step("Distribution"):
            dist = mgr._repo.resolve_distribution(name)

        with ui.step("Packs"):
            packs, mounts, tools = mgr._resolver.resolve(dist)
            ui.detail(", ".join(packs))

        with ui.step("Workspace"):
            root.mkdir(parents=True, exist_ok=True)
            mgr._materializer.materialize(root, dist.name, packs, mounts=mounts)

        with ui.step("Mounts"):
            for m in mounts:
                ui.detail(f"{m.pack} → {m.target}")

        with ui.step("Environment"):
            from datetime import UTC, datetime

            from y5n.apps.yak.installation.models import (
                Installation,
                InstallationStatus,
            )

            now = datetime.now(UTC)
            inst = Installation(
                name=name,
                distribution=dist.name,
                root=root,
                packs=packs,
                status=InstallationStatus.MATERIALIZED,
                created=now,
                updated=now,
            )
            mgr._write_state(inst)
            mgr._installer.install(inst, tools=tools, sdk_path=mgr._sdk_path)
            inst.status = InstallationStatus.CREATED
            inst.updated = datetime.now(UTC)
            mgr._write_state(inst)

        ui.ok(f"{name} ready at {root}")

    except Exception as e:
        ui.fail(f"Installation failed: {e}")


def _add_to_existing(args, mgr, ui, existing):
    name = args.artifact
    ui.title(f'Adding "{name}" to {existing.name}')

    try:
        with ui.step("Resolving"):
            inst = mgr.load(existing)
            if inst is None:
                raise RuntimeError("Installation not found")
            dist = mgr._repo.resolve_distribution(name)
            if dist is None:
                raise ValueError(f"Unknown pack: {name}")
            ui.detail(name)

        with ui.step("Packs"):
            new_packs, new_mounts, new_tools = mgr._resolver.resolve(dist)
            if not new_packs:
                from y5n.apps.yak.distribution.models import Mount, PackName

                new_packs = [PackName(name)]
                new_mounts = [
                    Mount(pack=PackName(name), target=f"/{name}")
                ]
            added = [p for p in new_packs if p not in inst.packs]
            if not added:
                ui.ok("Already installed")
                return
            all_packs = inst.packs + added
            ui.detail(", ".join(added))

        with ui.step("Workspace"):
            mgr._materializer.materialize(
                existing, inst.distribution, all_packs, mounts=new_mounts
            )

        with ui.step("Mounts"):
            for m in new_mounts:
                ui.detail(f"{m.pack} → {m.target}")

        with ui.step("Environment"):
            from datetime import UTC, datetime

            inst.packs = all_packs
            inst.updated = datetime.now(UTC)
            mgr._write_state(inst)
            mgr._installer.install(inst, sdk_path=mgr._sdk_path)
            inst.updated = datetime.now(UTC)
            mgr._write_state(inst)

        ui.ok(f"Added {name}")

    except Exception as e:
        ui.fail(f"Failed: {e}")
