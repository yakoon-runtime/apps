"""yak install <artifact> [<target>] — install an artifact or distribution."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI
from y5n.apps.yak.resolver.install import find_artifact, install_artifact


def run(args, mgr) -> None:
    name = getattr(args, "artifact", None)
    if not name:
        _list_environments(mgr)
        return

    ui = TerminalUI(verbose=getattr(args, "verbose", False))

    if mgr.is_distribution(name):
        _distribution_install(args, mgr, ui)
    else:
        _artifact_install(args, mgr, ui)


def _list_environments(mgr) -> None:
    environments = mgr.list_environments()
    if environments:
        print("  Available environments:")
        for name, desc in environments:
            desc_str = f"  — {desc}" if desc else ""
            print(f"    {name}{desc_str}")
    else:
        print("  No environments available.")
        print("  Run 'yak build <source>' to build artifacts first.")


def _artifact_install(args, mgr, ui) -> None:
    """Install a single artifact (built wheel) into the target root."""
    target = Path(args.target).resolve()
    upgrade = getattr(args, "upgrade", False)
    force = getattr(args, "force", False) or upgrade

    repositories = _repositories(args)
    artifact = find_artifact(args.artifact, sources=repositories)
    if artifact is None:
        ui.fail(f"Unknown target: {args.artifact}")
        return

    label = f"{args.artifact} {artifact.version or '?'}"

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
    if not ok:
        ui.fail(f"{label} install failed")
        return

    _write_environment(target, args.artifact, mgr)
    mgr.materialize_dev_workspace(args.artifact, target)
    from y5n.apps.yak.environment.io import touch

    touch(target, name=args.artifact)
    ui.ok(f"{label} installed at {target}")


def _repositories(args) -> list[str] | None:
    """Repositories: CLI --repository overrides, otherwise the context."""
    cli_repo = getattr(args, "repository", None)
    if cli_repo:
        return [cli_repo]

    from y5n.apps.yak.hosts.cli.cwd import Context

    ctx = Context.current()
    return list(ctx.repository_sources) if ctx else None


def _write_environment(root: Path, env_name: str, mgr) -> None:
    """Write .yak/environment.yml from a meta-artifact's workspace, if any."""
    from y5n.apps.yak.distribution.models import PackName
    from y5n.apps.yak.environment.io import load, save
    from y5n.apps.yak.environment.models import Environment
    from y5n.apps.yak.resolver.artifact import (
        DirectorySource,
        load_workspace_manifest,
    )
    from y5n.apps.yak.resolver.install import _collect_roots

    if load(root):
        return

    for artifact_root in _collect_roots(None):
        art = DirectorySource(artifact_root).resolve(env_name)
        if art is None or not art.is_meta() or art.manifest is None:
            continue
        ws = load_workspace_manifest(art.manifest)
        if ws is None:
            continue
        mounts = mgr.resolve_mount_sources(ws.mounts)
        env = Environment(
            name=env_name,
            dependencies=[PackName(p) for p in ws.dependencies],
            mounts=mounts,
        )
        save(env, root)
        return

    save(Environment(name=env_name), root)


def _distribution_install(args, mgr, ui) -> None:
    artifact = args.artifact
    target = Path(args.target).resolve()
    root = target / artifact

    from y5n.apps.yak.environment.io import env_path

    if env_path(root).exists():
        _add_to_existing(args, mgr, ui, root)
    else:
        _create_new(args, mgr, ui, artifact, root)


def _create_new(args, mgr, ui, name, root) -> None:
    from y5n.apps.yak.installation.ask import TerminalStoreAsker

    ui.title(f'Installing "{name}"')
    try:
        mgr.install(name, root, asker=TerminalStoreAsker(), ui=ui)
        ui.ok(f"{name} ready at {root}")
    except Exception as e:
        ui.fail(f"Installation failed: {e}")


def _add_to_existing(args, mgr, ui, root) -> None:
    from y5n.apps.yak.environment.io import load as load_env
    from y5n.apps.yak.installation.ask import TerminalStoreAsker

    name = args.artifact
    env = load_env(root)
    ui.title(f'Adding "{name}" to {env.name if env else root.name}')
    try:
        result = mgr.add(name, root, asker=TerminalStoreAsker(), ui=ui)
        if result is None:
            ui.ok("Already installed")
            return
        ui.ok(f"Added {name}")
    except Exception as e:
        ui.fail(f"Failed: {e}")
