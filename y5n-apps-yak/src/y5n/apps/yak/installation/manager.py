from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from y5n.apps.yak.distribution.models import PackName
from y5n.apps.yak.installation.models import Installation, InstallationStatus
from y5n.apps.yak.installer.installer import Installer
from y5n.apps.yak.repository.artifact import ArtifactStore
from y5n.apps.yak.repository.interface import Repository
from y5n.apps.yak.resolver.resolver import Resolver
from y5n.apps.yak.workspace.materializer import Materializer


class InstallationManager:
    def __init__(
        self,
        repository: Repository,
        artifact_store: ArtifactStore,
    ) -> None:
        self._repo = repository
        self._artifacts = artifact_store
        self._resolver = Resolver(lambda name: repository.resolve_distribution(name))
        self._materializer = Materializer(artifact_store)
        self._installer = Installer(artifact_store, apps_root=None)
        self._sdk_path = None

    # ── Install ──

    def install(self, target: str, path: Path) -> Installation:
        dist = self._repo.resolve_distribution(target)
        if dist is None:
            raise ValueError(f"Unknown target: {target}")

        packs, mounts, tools = self._resolver.resolve(dist)
        now = datetime.now(UTC)
        root = path.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._materializer.materialize(root, dist.name, packs, mounts=mounts)

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
            raise RuntimeError(f"Cannot update running installation: {name}")

        dist = self._repo.resolve_distribution(inst.distribution)
        if dist is None:
            raise ValueError(f"Distribution not found: {inst.distribution}")

        packs, mounts, tools = self._resolver.resolve(dist)
        now = datetime.now(UTC)
        self._materializer.materialize(inst.root, dist.name, packs, mounts=mounts)

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
            return ["Installation not found"]

        root = inst.root
        if not root.exists():
            issues.append("Installation root missing")

        if not (root / ".yak" / "state.toml").exists():
            issues.append("state.toml missing")

        # Pack checks (from state.toml)
        for pack in inst.packs:
            if not self._artifacts.has_artifact(pack):
                issues.append(f"Pack '{pack}' not found")

        # Environment checks (optional — env may not exist in older installs)
        from y5n.apps.yak.environment.io import load as load_env

        env = load_env(root)
        if env is None:
            issues.append(".yak/environment.yml missing or invalid")
        else:
            if not env.mounts:
                issues.append("no mounts defined in environment.yml")
            for mount in env.mounts:
                artifact = self._artifacts.get_artifact(mount.pack)
                if artifact is None:
                    issues.append(
                        f"mount '{mount.pack}' → '{mount.target}': pack not found"
                    )
                else:
                    struct = artifact / "structure"
                    if not struct.is_dir():
                        issues.append(f"mount '{mount.pack}': no structure/ directory")

        # Workspace checks
        ws_path = root / "structure"
        if not ws_path.is_dir():
            issues.append("workspace/structure/ missing")
        elif env and env.mounts:
            for mount in env.mounts:
                target = (
                    ws_path / mount.target.strip("/")
                    if mount.target != "/"
                    else ws_path
                )
                if not target.exists():
                    issues.append(
                        f"workspace mount '{mount.pack}' → '{mount.target}': symlink missing"
                    )
                elif target.is_symlink() and not target.resolve().exists():
                    issues.append(
                        f"workspace mount '{mount.pack}': broken symlink at {target}"
                    )

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
