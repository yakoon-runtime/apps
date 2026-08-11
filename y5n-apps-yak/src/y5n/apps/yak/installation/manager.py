from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from y5n.apps.yak.distribution.models import PackName
from y5n.apps.yak.installation.assemble import (
    build_memory_installation,
    collect_declared_stores,
)
from y5n.apps.yak.installation.models import Installation, InstallationStatus
from y5n.apps.yak.installer.installer import Installer
from y5n.apps.yak.repository.artifact import ArtifactStore
from y5n.apps.yak.repository.interface import Repository
from y5n.apps.yak.resolver.resolver import Resolver
from y5n.apps.yak.workspace.materializer import Materializer
from y5n.runtime.engine.installation import to_dict


class InstallationManager:
    def __init__(
        self,
        repository: Repository,
        artifact_store: ArtifactStore,
    ) -> None:
        self._repo = repository
        self._artifacts = artifact_store
        self._resolver = Resolver(lambda name: repository.resolve_distribution(name))
        self._materializer = Materializer()
        self._installer = Installer(artifact_store, apps_root=None)
        self._sdk_path = None

    # ── Install ──

    def install(self, target: str, path: Path) -> Installation:
        dist = self._repo.resolve_distribution(target)
        if dist is None:
            raise ValueError(f"Unknown target: {target}")

        packs, tools = self._resolver.resolve(dist)
        mounts = self._resolve_mount_sources(dist.mounts)
        now = datetime.now(UTC)
        root = path.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._materializer.materialize(root / "structure", dist.name, mounts=mounts)
        self._assemble(root / "structure", root / ".yak")

        inst = Installation(
            name=target,
            distribution=dist.name,
            root=root,
            packs=packs,
            status=InstallationStatus.MATERIALIZED,
            created=now,
            updated=now,
        )
        self._write_state(inst)

        self._installer.install(inst, tools=tools, sdk_path=self._sdk_path)
        inst.status = InstallationStatus.CREATED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)
        return inst

    # ── Update ──

    def update(self, path: Path) -> Installation:
        inst = self.load(path)
        if inst is None:
            raise ValueError(f"Installation not found: {path}")

        if inst.status == InstallationStatus.RUNNING:
            raise RuntimeError(f"Cannot update running installation: {inst.name}")

        dist = self._repo.resolve_distribution(inst.distribution)
        if dist is None:
            raise ValueError(f"Distribution not found: {inst.distribution}")

        packs, tools = self._resolver.resolve(dist)
        mounts = self._resolve_mount_sources(dist.mounts)
        now = datetime.now(UTC)
        self._materializer.materialize(
            inst.root / "structure", dist.name, mounts=mounts
        )

        inst.packs = packs
        inst.status = InstallationStatus.MATERIALIZED
        inst.updated = now
        self._write_state(inst)

        self._installer.install(inst, tools=tools, sdk_path=self._sdk_path)
        inst.status = InstallationStatus.CREATED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)
        return inst

    # ── Doctor ──

    def doctor(self, path: Path) -> list[str]:
        issues: list[str] = []
        inst = self.load(path)
        if inst is None:
            return ["✘ Installation   not found"]

        root = inst.root

        # Context
        if not root.exists():
            issues.append("✘ Context       root missing")
        else:
            issues.append(f"✓ Context       {root}")

        if not (root / ".yak" / "state.toml").exists():
            issues.append("✘ State         .yak/state.toml missing")
        else:
            issues.append("✓ State         .yak/state.toml")

        # Environment
        from y5n.apps.yak.environment.io import load as load_env

        env = load_env(root)
        if env is None:
            issues.append("✘ Environment   .yak/environment.yml missing")
        else:
            issues.append(
                f"✓ Environment   {len(env.mounts)} mount(s), {len(env.dependencies)} dep(s)"
            )

        # Packs from state
        if inst.packs:
            for pack in inst.packs:
                if self._artifacts.has_artifact(pack):
                    issues.append(f"✓ Pack          {pack}")
                else:
                    issues.append(f"✘ Pack          {pack} not found")

        # Mount resolution
        if env:
            for mount in env.mounts:
                source = Path(mount.source)
                if not source.exists():
                    issues.append(
                        f"✘ Mount         {mount.source} → {mount.target}: not found"
                    )
                else:
                    issues.append(f"✓ Mount         {mount.target} ← {mount.source}")

        # Workspace
        ws_path = root / "structure"
        if not ws_path.is_dir():
            issues.append("✘ Workspace     structure/ missing")
        elif env and env.mounts:
            issues.append(f"✓ Workspace     {ws_path}")
            for mount in env.mounts:
                target = (
                    ws_path / mount.target.strip("/")
                    if mount.target != "/"
                    else ws_path
                )
                if not target.exists():
                    issues.append(
                        f"✘ Symlink       {mount.pack} → {mount.target}: missing"
                    )
                elif target.is_symlink() and not target.resolve().exists():
                    issues.append(f"✘ Symlink       {mount.pack}: broken at {target}")

        # Fingerprint check (compare installed vs current artifact)
        from y5n.apps.yak.resolver.install import _fingerprint_matches

        for pack in inst.packs:
            artifact = self._artifacts.get_artifact(pack)
            if artifact is not None:
                if _fingerprint_matches(artifact, root):
                    issues.append(f"✓ Fingerprint   {pack} current")
                else:
                    issues.append(f"✘ Fingerprint   {pack} outdated — run 'yak sync'")

        # Runtime
        pid_file = root / ".yak" / "runtime.pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            try:
                os.kill(int(pid), 0)
                issues.append(f"✓ Runtime       running (pid {pid})")
            except (OSError, ValueError):
                issues.append(
                    "✘ Runtime       pid file stale — run 'yak runtime restart'"
                )
        else:
            issues.append("— Runtime       not running")

        return issues

    # ── Run / Stop ──

    def run(self, path: Path) -> None:
        inst = self.load(path)
        if inst is None:
            raise ValueError(f"Installation not found: {path}")

        runtime_dir = self._artifacts.get_artifact(PackName("runtime"))
        if runtime_dir is None:
            raise RuntimeError("Runtime artifact not found")

        main = runtime_dir / "boot" / "python" / "__main__.py"
        if not main.exists():
            raise RuntimeError(f"Runtime entry not found: {main}")

        subprocess.Popen(
            [sys.executable, str(main)],
            cwd=inst.root,
        )

        inst.status = InstallationStatus.RUNNING
        inst.updated = datetime.now(UTC)
        self._write_state(inst)

    def stop(self, path: Path) -> None:
        inst = self.load(path)
        if inst is None:
            raise ValueError(f"Installation not found: {path}")

        import signal

        pid_file = inst.root / ".yak" / "runtime.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            pid_file.unlink(missing_ok=True)

        inst.status = InstallationStatus.STOPPED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)

    def load(self, path: Path) -> Installation | None:
        """Load an installation from an arbitrary path."""
        state_file = path / ".yak" / "state.toml"
        if not state_file.exists():
            return None
        return self._read_state(state_file)

    # ── Mount resolution ──

    def _resolve_mount_sources(self, mounts: list) -> list:
        """Convert pack-name mounts to source-path mounts using artifact store."""
        from y5n.apps.yak.distribution.models import Mount, PackName

        resolved = []
        for m in mounts:
            pack_name = m.source if hasattr(m, "source") else getattr(m, "pack", "")
            if not pack_name:
                continue
            artifact = self._artifacts.get_artifact(PackName(pack_name))
            if artifact and (artifact / "structure").is_dir():
                resolved.append(
                    Mount(
                        source=str((artifact / "structure").resolve()),
                        target=m.target,
                    )
                )
        return resolved

    # ── Assembly (ADR-19) ──

    def _assemble(self, structure_dir: Path, installation_dir: Path) -> None:
        """Materialize the deployment from the declared stores.

        The installation binds the runtime's own `runtime` store plus
        every store the installed packs declare, each to its StoreFactory
        and config. It is written to `.yak/deployment.yml` —
        machine-specific, not versioned, owned by `yak`.
        """
        stores = collect_declared_stores(structure_dir)
        installation = build_memory_installation(stores)
        installation_dir.mkdir(parents=True, exist_ok=True)

        with open(installation_dir / "deployment.yml", "w") as f:
            yaml.safe_dump(to_dict(installation), f, sort_keys=False)

    # ── Internals ──

    def _write_state(self, inst: Installation) -> None:
        state_dir = inst.root / ".yak"
        state_dir.mkdir(parents=True, exist_ok=True)
        manifest = f"""\
[installation]
name = "{inst.name}"
distribution = "{inst.distribution}"
status = "{inst.status.value}"
packs = [{", ".join(f'"{p}"' for p in inst.packs)}]
created = "{inst.created.isoformat() if inst.created else ""}"
updated = "{inst.updated.isoformat() if inst.updated else ""}"
"""
        (state_dir / "state.toml").write_text(manifest)

    def _read_state(self, path: Path) -> Installation | None:
        import tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)
        inst_data = data.get("installation", {})
        if not inst_data:
            return None
        return Installation(
            name=inst_data.get("name", ""),
            distribution=inst_data.get("distribution", ""),
            root=path.parent.parent,
            packs=[PackName(p) for p in inst_data.get("packs", [])],
            status=InstallationStatus(inst_data.get("status", "created")),
            created=self._parse_dt(inst_data.get("created")),
            updated=self._parse_dt(inst_data.get("updated")),
        )

    @staticmethod
    def _parse_dt(raw: str | None) -> datetime | None:
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        return None
