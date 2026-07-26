"""yak install <artifact> [<target>] — install an artifact or distribution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI
from y5n.apps.yak.resolver.artifact import _parse_manifest
from y5n.apps.yak.resolver.install import _collect_roots, install_artifact


def run(args, mgr) -> None:
    name = getattr(args, "artifact", None)
    if not name:
        _list_environments()
        return

    ui = TerminalUI(verbose=getattr(args, "verbose", False))

    if _is_distribution(name, mgr):
        _distribution_install(args, mgr, ui)
    else:
        _artifact_install(args, mgr, ui)


def _list_environments() -> None:
    from pathlib import Path

    seen: set[str] = set()
    names: list[str] = []

    # Bundled environments
    bundle_dir = Path(__file__).resolve().parents[7] / "artifacts"
    if bundle_dir.is_dir():
        for f in sorted(bundle_dir.iterdir()):
            if f.suffix == ".yml":
                meta = _parse_manifest(f)
                if meta.get("kind") == "meta":
                    name = meta.get("name", "")
                    desc = meta.get("description", "")
                    if name and name not in seen:
                        seen.add(name)
                        names.append((name, desc))

    if names:
        print("  Available environments:")
        for name, desc in names:
            desc_str = f"  — {desc}" if desc else ""
            print(f"    {name}{desc_str}")
    else:
        print("  No environments available.")
        print("  Run 'yak build <source>' to build artifacts first.")


def _artifact_install(args, mgr, ui) -> None:
    target = Path(args.target).resolve()
    ok = ui.task(
        "Artifacts", lambda: install_artifact(args.artifact, target_root=target)
    )
    if ok:
        _write_artifact_state(args.artifact, target)
        _materialize_dev_workspace(args.artifact, target, mgr)
        ui.ok(f"Installed {args.artifact} at {target}")
    else:
        ui.fail(f"Unknown target: {args.artifact}")


def _materialize_dev_workspace(name: str, root: Path, mgr) -> None:
    """Materialize workspace from the artifact's manifest, if configured."""
    from y5n.apps.yak.distribution.models import Mount, PackName
    from y5n.apps.yak.resolver.artifact import DirectorySource

    for artifact_root in _collect_roots(None):
        source = DirectorySource(artifact_root)
        art = source.resolve(name)
        if art and art.kind == "meta" and art.path:
            manifest = art.path / "artifact.yml"
            if manifest.exists():
                import yaml

                data = yaml.safe_load(manifest.read_text())
                ws = data.get("workspace")
                if ws:
                    packs = [PackName(p) for p in ws.get("packs", [])]
                    mounts = [
                        Mount(pack=PackName(m["pack"]), target=m["target"])
                        for m in ws.get("mounts", [])
                    ]
                    mgr._materializer.materialize(root, name, packs, mounts=mounts)
                    return


def _write_artifact_state(name: str, root: Path) -> None:
    """Write .yak/state.toml to mark this as a Yakoon installation."""
    yak_dir = root / ".yak"
    yak_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    state = f"""\
[installation]
name = "{name}"
distribution = "{name}"
status = "created"
packs = ["root", "boot", "system"]
created = "{now}"
updated = "{now}"
"""
    (yak_dir / "state.toml").write_text(state)


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
                new_mounts = [Mount(pack=PackName(name), target=f"/{name}")]
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
