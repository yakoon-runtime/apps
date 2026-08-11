from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import yaml
from y5n.apps.yak.distribution.models import Mount, PackName
from y5n.apps.yak.environment.io import touch
from y5n.apps.yak.installation.assemble import (
    StoreAsker,
    assemble_installation,
    collect_declared_stores,
)
from y5n.apps.yak.installation.models import Installation, InstallationStatus
from y5n.apps.yak.installer.installer import Installer
from y5n.apps.yak.repository.artifact import ArtifactStore
from y5n.apps.yak.repository.interface import Repository
from y5n.apps.yak.resolver.resolver import Resolver
from y5n.apps.yak.workspace.materializer import Materializer
from y5n.runtime.engine.installation import Installation as RuntimeInstallation
from y5n.runtime.engine.installation import load_installation, to_dict


class InstallationManager:
    def __init__(
        self,
        repository: Repository,
        artifact_store: ArtifactStore,
        *,
        sdk_path: Path | None = None,
        apps_root: Path | None = None,
        runtime_root: Path | None = None,
    ) -> None:
        self._repo = repository
        self._artifacts = artifact_store
        self._resolver = Resolver(lambda name: repository.resolve_distribution(name))
        self._materializer = Materializer()
        self._installer = Installer(
            artifact_store, apps_root=apps_root, runtime_root=runtime_root
        )
        self._sdk_path = sdk_path

    # ── Install ──

    def install(
        self,
        target: str,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
    ) -> Installation:
        """Install a distribution into a fresh root.

        ``asker`` guides the store mapping interactively; ``ui`` reports
        progress. Without them the flow runs silently with memory
        backends.
        """
        with self._step(ui, "Distribution"):
            dist = self._repo.resolve_distribution(target)
            if dist is None:
                raise ValueError(f"Unknown target: {target}")

        with self._step(ui, "Packs"):
            packs, tools = self._resolver.resolve(dist)

        now = datetime.now(UTC)
        root = path.resolve()
        with self._step(ui, "Workspace"):
            root.mkdir(parents=True, exist_ok=True)
            mounts = self.resolve_mount_sources(dist.mounts)
            self._materializer.materialize(root / "structure", dist.name, mounts=mounts)

        self._report_mounts(ui, mounts)

        with self._step(ui, "Deployment"):
            self._assemble(root / "structure", root / ".yak", asker=asker)

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

        with self._step(ui, "Installing"):
            self._installer.install(inst, tools=tools, sdk_path=self._sdk_path)

        with self._step(ui, "Environment"):
            touch(root, name=target, dependencies=packs, mounts=mounts)

        inst.status = InstallationStatus.CREATED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)
        return inst

    # ── Add ──

    def add(
        self,
        target: str,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
    ) -> Installation | None:
        """Add a distribution to an existing environment.

        Returns None when everything is already installed.
        """
        with self._step(ui, "Resolving"):
            from y5n.apps.yak.environment.io import load as load_env

            env = load_env(path)
            if env is None:
                raise RuntimeError(f"No environment found at {path}")
            existing_packs = list(env.dependencies)

            dist = self._repo.resolve_distribution(target)
            if dist is None:
                raise ValueError(f"Unknown pack: {target}")

        with self._step(ui, "Packs"):
            new_packs, new_tools = self._resolver.resolve(dist)
            if not new_packs:
                new_packs = [PackName(target)]
            added = [p for p in new_packs if p not in existing_packs]
            if not added:
                return None
            all_packs = existing_packs + added

        with self._step(ui, "Workspace"):
            mounts = self.resolve_mount_sources(dist.mounts)
            if not mounts:
                artifact = self._artifacts.get_artifact(PackName(target))
                if artifact and (artifact / "structure").is_dir():
                    mounts = [
                        Mount(
                            source=str((artifact / "structure").resolve()),
                            target=f"/{target}",
                        )
                    ]
            self._materializer.materialize(path / "structure", env.name, mounts=mounts)

        self._report_mounts(ui, mounts)

        with self._step(ui, "Deployment"):
            existing = load_installation(path / ".yak" / "deployment.yml")
            self._assemble(
                path / "structure", path / ".yak", existing=existing, asker=asker
            )

        now = datetime.now(UTC)
        inst = Installation(
            name=target,
            distribution=dist.name,
            root=path.resolve(),
            packs=all_packs,
            status=InstallationStatus.MATERIALIZED,
            created=now,
            updated=now,
        )
        self._write_state(inst)

        with self._step(ui, "Installing"):
            self._installer.install(inst, sdk_path=self._sdk_path)

        with self._step(ui, "Environment"):
            merged = list(env.mounts) + [m for m in mounts if m not in env.mounts]
            touch(path, name=env.name, dependencies=all_packs, mounts=merged)

        inst.status = InstallationStatus.CREATED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)
        return inst

    # ── Update ──

    def update(
        self,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
    ) -> Installation:
        with self._step(ui, "Distribution"):
            inst = self.load(path)
            if inst is None:
                raise ValueError(f"Installation not found: {path}")
            if inst.status == InstallationStatus.RUNNING:
                raise RuntimeError(f"Cannot update running installation: {inst.name}")

            dist = self._repo.resolve_distribution(inst.distribution)
            if dist is None:
                raise ValueError(f"Distribution not found: {inst.distribution}")

        with self._step(ui, "Packs"):
            packs, tools = self._resolver.resolve(dist)

        now = datetime.now(UTC)
        with self._step(ui, "Workspace"):
            mounts = self.resolve_mount_sources(dist.mounts)
            self._materializer.materialize(
                inst.root / "structure", dist.name, mounts=mounts
            )

        self._report_mounts(ui, mounts)

        with self._step(ui, "Deployment"):
            # Preserve the operator's bindings; only newly declared stores
            # are (re)assembled.
            existing = load_installation(inst.root / ".yak" / "deployment.yml")
            self._assemble(
                inst.root / "structure",
                inst.root / ".yak",
                existing=existing,
                asker=asker,
            )

        inst.packs = packs
        inst.status = InstallationStatus.MATERIALIZED
        inst.updated = now
        self._write_state(inst)

        with self._step(ui, "Installing"):
            self._installer.install(inst, tools=tools, sdk_path=self._sdk_path)

        with self._step(ui, "Environment"):
            touch(inst.root, name=inst.name, dependencies=packs, mounts=mounts)

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
                        f"✘ Symlink       {mount.source} → {mount.target}: missing"
                    )
                elif target.is_symlink() and not target.resolve().exists():
                    issues.append(f"✘ Symlink       {mount.source}: broken at {target}")

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

    def resolve_mount_sources(self, mounts: list) -> list:
        """Convert pack-name or repo-relative mounts to source-path mounts.

        A mount source is either a pack name (resolved through the
        artifact store) or a repo-relative path like
        ``packs/y5n-packs-ident/structure`` (resolved against the
        repository roots).
        """
        resolved = []
        for m in mounts:
            if isinstance(m, dict):
                source = m.get("source") or m.get("pack") or ""
                target = m.get("target", "")
            else:
                source = m.source if hasattr(m, "source") else getattr(m, "pack", "")
                target = getattr(m, "target", "")
            if not source:
                continue
            artifact_root = self._resolve_source(source)
            if artifact_root is None:
                continue
            structure = artifact_root / "structure"
            if not structure.is_dir():
                structure = artifact_root
            resolved.append(Mount(source=str(structure.resolve()), target=target))
        return resolved

    def _resolve_source(self, source: str) -> Path | None:
        """Resolve a mount source — a pack name or a repo-relative path."""
        artifact = self._artifacts.get_artifact(PackName(source))
        if artifact is not None:
            return artifact
        s = Path(source)
        if s.is_absolute() and s.is_dir():
            return s
        for root in self._repo.roots():
            candidate = root / s
            if candidate.is_dir():
                return candidate
        return None

    # ── Assembly (ADR-19) ──

    def _assemble(
        self,
        structure_dir: Path,
        installation_dir: Path,
        existing: RuntimeInstallation | None = None,
        asker: StoreAsker | None = None,
    ) -> None:
        """Materialize the deployment from the declared stores.

        The installation binds the runtime's own `runtime` store plus
        every store the installed packs declare, each to its StoreFactory
        and config. It is written to `.yak/deployment.yml` —
        machine-specific, not versioned, owned by `yak`.

        Existing bindings are preserved on update; with an asker the
        operator guides the mapping for newly declared stores.
        """
        stores = collect_declared_stores(structure_dir)
        try:
            installation = assemble_installation(stores, existing=existing, asker=asker)
        except EOFError:
            # Non-interactive context: fall back to the memory defaults.
            installation = assemble_installation(stores, existing=existing)
        installation_dir.mkdir(parents=True, exist_ok=True)

        with open(installation_dir / "deployment.yml", "w") as f:
            yaml.safe_dump(to_dict(installation), f, sort_keys=False)

    # ── Introspection ──

    def is_distribution(self, name: str) -> bool:
        return self._repo.resolve_distribution(name) is not None

    def list_environments(self) -> list[tuple[str, str]]:
        """List the bundled meta distributions (installable environments)."""
        from y5n.apps.yak.resolver.artifact import _parse_manifest

        d = self._repo.builtin_artifacts_dir()
        if d is None or not d.is_dir():
            return []
        environments: list[tuple[str, str]] = []
        for f in sorted(d.glob("*.yml")):
            meta = _parse_manifest(f)
            if meta.get("kind") == "meta":
                name = meta.get("name", "")
                if name:
                    environments.append((name, meta.get("description", "")))
        return environments

    def materialize_dev_workspace(self, name: str, root: Path) -> None:
        """Materialize a workspace from a meta-artifact's manifest, if any."""
        from y5n.apps.yak.resolver.artifact import (
            DirectorySource,
            load_workspace_manifest,
        )
        from y5n.apps.yak.resolver.install import _collect_roots

        for artifact_root in _collect_roots(None):
            art = DirectorySource(artifact_root).resolve(name)
            if art is None or not art.is_meta() or art.manifest is None:
                continue
            ws = load_workspace_manifest(art.manifest)
            if ws is None:
                continue
            resolved = self.resolve_mount_sources(ws.mounts)
            self._materializer.materialize(root / "structure", name, mounts=resolved)
            return

    # ── Internals ──

    @contextmanager
    def _step(self, ui, label: str):
        if ui is None:
            yield
            return
        with ui.step(label):
            yield

    @staticmethod
    def _detail(ui, text: str) -> None:
        if ui is not None:
            ui.detail(text)

    def _report_mounts(self, ui, mounts: list) -> None:
        with self._step(ui, "Mounts"):
            for m in mounts:
                self._detail(ui, f"{m.target} ← {m.source}")

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
