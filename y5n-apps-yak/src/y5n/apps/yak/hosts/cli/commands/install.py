"""yak install <artifact> [<target>] — install an artifact or distribution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI
from y5n.apps.yak.resolver.artifact import _parse_manifest
from y5n.apps.yak.resolver.install import (
    _collect_roots,
    find_artifact,
    install_artifact,
)


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
    upgrade = getattr(args, "upgrade", False)
    force = getattr(args, "force", False) or upgrade

    # Repositories: CLI --repository overrides, otherwise use context
    from y5n.apps.yak.hosts.cli.cwd import Context

    repositories = []
    cli_repo = getattr(args, "repository", None)
    if cli_repo:
        repositories.append(cli_repo)
    else:
        ctx = Context.current()
        if ctx:
            repositories = list(ctx.repository_sources)

    repositories = repositories or None

    artifact = find_artifact(args.artifact, sources=repositories)
    if artifact is None:
        ui.fail(f"Unknown target: {args.artifact}")
        return

    version = artifact.version or "?"
    label = f"{args.artifact} {version}"

    # Check if already installed
    from y5n.apps.yak.resolver.install import _fingerprint_matches

    if not force and _fingerprint_matches(artifact, target):
        ui.ok(f"{label} already up to date")
        return

    ok = ui.task(
        "Artifacts",
        lambda: install_artifact(
            args.artifact,
            target_root=target,
            force=force,
            sources=repositories,
        ),
    )
    if ok:
        _mark_installed(args.artifact, target)
        _materialize_dev_workspace(args.artifact, target, mgr)
        _write_environment(target, args.artifact)
        ui.ok(f"{label} installed at {target}")
    else:
        ui.fail(f"{label} install failed")


def _resolve_mount_sources(root: Path, mounts: list, mgr) -> list:
    """Convert pack-name mounts to source-path mounts using artifact store."""
    from y5n.apps.yak.distribution.models import Mount, PackName

    resolved = []
    for m in mounts:
        pack_name = m.source if hasattr(m, "source") else getattr(m, "pack", "")
        artifact = mgr._artifacts.get_artifact(PackName(pack_name))
        if artifact and (artifact / "structure").is_dir():
            resolved.append(
                Mount(
                    source=str((artifact / "structure").resolve()),
                    target=m.target,
                )
            )
    return resolved


def _write_environment(root: Path, env_name: str) -> None:
    """Write .yak/environment.yml from context or template."""
    from y5n.apps.yak.distribution.models import Mount, PackName
    from y5n.apps.yak.environment.io import load, save
    from y5n.apps.yak.environment.models import Environment
    from y5n.apps.yak.resolver.artifact import DirectorySource
    from y5n.apps.yak.resolver.install import _collect_roots

    existing = load(root)
    if existing:
        return

    # Try to read workspace config from installed meta-artifact
    for artifact_root in _collect_roots(None):
        source = DirectorySource(artifact_root)
        art = source.resolve(env_name)
        if art and art.kind == "meta" and art.path:
            import yaml

            manifest = art.path / "artifact.yml"
            if manifest.exists():
                data = yaml.safe_load(manifest.read_text())
                ws = data.get("workspace", {})
                if ws:
                    deps = [PackName(p) for p in data.get("dependencies", [])]
                    mounts = [
                        Mount(
                            source=str(
                                (source_dir / m["pack"] / "structure").resolve()
                            ),
                            target=m["target"],
                        )
                        for m in ws.get("mounts", [])
                        for source_dir in _collect_roots(None)
                        if (source_dir / m["pack"] / "structure").is_dir()
                    ]
                    env = Environment(
                        name=env_name,
                        dependencies=deps,
                        mounts=mounts,
                    )
                    save(env, root)
                    return

    # Fallback: minimal env
    save(Environment(name=env_name), root)


def _materialize_dev_workspace(name: str, root: Path, mgr) -> None:
    """Materialize workspace from the artifact's manifest, if configured."""
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
                    raw_mounts = [
                        {"pack": m["pack"], "target": m["target"]}
                        for m in ws.get("mounts", [])
                    ]
                    resolved = _resolve_mount_sources(root, raw_mounts, mgr)
                    mgr._materializer.materialize(
                        root / "structure", name, mounts=resolved
                    )
                    return


def _mark_installed(name: str, root: Path, packs: list | None = None) -> None:
    """Write installation metadata to .yak/environment.yml."""
    from datetime import UTC, datetime

    from y5n.apps.yak.environment.io import load, save

    env = load(root)
    if env is None:
        from y5n.apps.yak.environment.models import Environment

        env = Environment(name=name)
    now = datetime.now(UTC)
    env.created = env.created or now
    env.updated = now
    if packs:
        from y5n.apps.yak.distribution.models import PackName

        env.dependencies = [PackName(p) for p in packs]
    save(env, root)


def _distribution_install(args, mgr, ui) -> None:
    artifact = args.artifact
    target = Path(args.target).resolve()
    root = target / artifact

    existing = root if (root / ".yak" / "environment.yml").exists() else None

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
            packs, tools = mgr._resolver.resolve(dist)
            ui.detail(", ".join(packs))

        with ui.step("Workspace"):
            root.mkdir(parents=True, exist_ok=True)
            resolved = _resolve_mount_sources(root, dist.mounts, mgr)
            mgr._materializer.materialize(
                root / "structure", dist.name, mounts=resolved
            )

        with ui.step("Mounts"):
            for m in resolved:
                ui.detail(f"{m.target} ← {m.source}")

        with ui.step("Installing"):
            from y5n.apps.yak.installation.models import (
                Installation,
                InstallationStatus,
            )

            inst = Installation(
                name=name,
                distribution=dist.name,
                root=root,
                packs=packs,
                status=InstallationStatus.MATERIALIZED,
            )
            mgr._installer.install(inst, tools=tools, sdk_path=mgr._sdk_path)

        with ui.step("Environment"):
            from y5n.apps.yak.environment.io import save
            from y5n.apps.yak.environment.models import Environment

            env = Environment(name=name, dependencies=list(packs), mounts=resolved)
            save(env, root)
            _mark_installed(name, root, packs)

        ui.ok(f"{name} ready at {root}")

    except Exception as e:
        ui.fail(f"Installation failed: {e}")


def _add_to_existing(args, mgr, ui, existing):
    name = args.artifact
    ui.title(f'Adding "{name}" to {existing.name}')

    try:
        with ui.step("Resolving"):
            from y5n.apps.yak.environment.io import load as load_env

            env = load_env(existing)
            if env is None:
                raise RuntimeError("No environment found")
            existing_packs = list(env.dependencies)

            dist = mgr._repo.resolve_distribution(name)
            if dist is None:
                raise ValueError(f"Unknown pack: {name}")
            ui.detail(name)

        with ui.step("Packs"):
            new_packs, new_tools = mgr._resolver.resolve(dist)
            from y5n.apps.yak.distribution.models import PackName

            if not new_packs:
                new_packs = [PackName(name)]
            added = [p for p in new_packs if p not in existing_packs]
            if not added:
                ui.ok("Already installed")
                return
            all_packs = existing_packs + added
            ui.detail(", ".join(added))

        with ui.step("Workspace"):
            resolved = _resolve_mount_sources(existing, dist.mounts, mgr)
            if not resolved:
                from y5n.apps.yak.distribution.models import Mount

                artifact = mgr._artifacts.get_artifact(PackName(name))
                if artifact and (artifact / "structure").is_dir():
                    resolved = [
                        Mount(
                            source=str((artifact / "structure").resolve()),
                            target=f"/{name}",
                        )
                    ]
            mgr._materializer.materialize(
                existing / "structure", env.name, mounts=resolved
            )

        with ui.step("Mounts"):
            for m in resolved:
                ui.detail(f"{m.target} ← {m.source}")

        with ui.step("Environment"):
            from y5n.apps.yak.installation.models import (
                Installation,
                InstallationStatus,
            )

            inst = Installation(
                name=name,
                distribution=dist.name,
                root=existing,
                packs=all_packs,
                status=InstallationStatus.MATERIALIZED,
            )
            mgr._installer.install(inst, sdk_path=mgr._sdk_path)
            _mark_installed(name, existing, all_packs)

        ui.ok(f"Added {name}")

    except Exception as e:
        ui.fail(f"Failed: {e}")
