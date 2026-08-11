from __future__ import annotations

import os
import signal
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from y5n.apps.yak.environment.io import touch
from y5n.apps.yak.installation.assemble import (
    StoreAsker,
    assemble_installation,
    collect_declared_stores,
)
from y5n.apps.yak.installation.models import Installation, InstallationStatus
from y5n.apps.yak.installer.installer import Installer
from y5n.apps.yak.pack.models import Mount, Pack, PackName, ToolReference
from y5n.apps.yak.repository.artifact import ArtifactStore
from y5n.apps.yak.repository.interface import Repository
from y5n.apps.yak.resolver.artifact import Artifact
from y5n.apps.yak.workspace.materializer import Materializer
from y5n.runtime.engine.installation import Installation as RuntimeInstallation
from y5n.runtime.engine.installation import load_installation, to_dict


@dataclass(frozen=True)
class _Component:
    """A resolved installable: a pack, an artifact or a tool (host app)."""

    kind: str
    name: str
    pack: Pack | None = None
    artifact: Artifact | None = None
    tool: ToolReference | None = None


class InstallationManager:
    def __init__(
        self,
        repository: Repository,
        artifact_store: ArtifactStore,
        *,
        sdk_path: Path | None = None,
        apps_root: Path | None = None,
        runtime_root: Path | None = None,
        packs_root: Path | None = None,
    ) -> None:
        self._repo = repository
        self._artifacts = artifact_store
        self._materializer = Materializer()
        self._installer = Installer(
            artifact_store, apps_root=apps_root, runtime_root=runtime_root
        )
        self._sdk_path = sdk_path
        self._packs_root = packs_root
        self._runtime_root = runtime_root

    # ── Install ──

    def install(
        self,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
    ) -> Installation:
        """Install the minimal Yakoon platform into ``path``.

        The platform is the runtime, the SDK and the host apps only — no
        packs. What the installation can do is decided afterwards with
        ``yak add``.
        """
        now = datetime.now(UTC)
        root = path.resolve()
        name = root.name or "yakoon"
        with self._step(ui, "Workspace"):
            root.mkdir(parents=True, exist_ok=True)
            mounts = self._platform_mounts()
            self._materializer.materialize(root / "structure", mounts=mounts)

        with self._step(ui, "Deployment"):
            self._assemble(root / "structure", root / ".yak", asker=asker)

        inst = Installation(
            name=name,
            root=root,
            packs=[],
            status=InstallationStatus.MATERIALIZED,
            created=now,
            updated=now,
        )
        self._write_state(inst)

        with self._step(ui, "Installing"):
            from y5n.apps.yak.installer.installer import PLATFORM_TOOLS

            self._installer.install(inst, tools=PLATFORM_TOOLS, sdk_path=self._sdk_path)

        with self._step(ui, "Environment"):
            touch(root, name=name, dependencies=[], mounts=mounts)

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
        sources: list[str] | None = None,
        force: bool = False,
    ) -> Installation | None:
        """Add a component (a pack or an artifact) to an installation.

        Both share one reconciliation: resolve → make available →
        materialize → discover requirements → reconcile deployment →
        persist. Only "make available" differs — a pack is built
        from its source, an artifact installs its payload. Returns
        None when the component is already part of the installation.
        """
        with self._step(ui, "Resolving"):
            from y5n.apps.yak.environment.io import load as load_env

            env = load_env(path)
            if env is None:
                raise RuntimeError(f"No installation found at {path}")
            existing_packs = list(env.dependencies)

            component = self._resolve_component(target, sources=sources)
            if component is None:
                raise ValueError(f"Unknown component: {target}")

        with self._step(ui, "Making available"):
            made = self._make_available(
                component, target, path, existing_packs, force, sources
            )
            if made is None:
                return None
            all_packs, mounts = made

        structure_dir = path / env.workspace_path

        with self._step(ui, "Materializing"):
            self._materializer.materialize(structure_dir, mounts=mounts)

        self._report_mounts(ui, mounts)

        with self._step(ui, "Deployment"):
            existing = load_installation(path / ".yak" / "deployment.yml")
            self._assemble(structure_dir, path / ".yak", existing=existing, asker=asker)

        existing_inst = self.load(path)
        now = datetime.now(UTC)
        inst = Installation(
            name=existing_inst.name if existing_inst else target,
            root=path.resolve(),
            packs=all_packs,
            status=InstallationStatus.MATERIALIZED,
            created=now,
            updated=now,
        )
        self._write_state(inst)

        with self._step(ui, "Environment"):
            merged = list(env.mounts) + [m for m in mounts if m not in env.mounts]
            touch(path, name=env.name, dependencies=all_packs, mounts=merged)

        inst.status = InstallationStatus.CREATED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)
        return inst

    def _resolve_component(
        self, target: str, *, sources: list[str] | None = None
    ) -> _Component | None:
        """Resolve a name to a pack, a built artifact or a tool (host app)."""
        pack = self._repo.resolve_pack(target)
        if pack is not None:
            return _Component(kind="pack", name=pack.name, pack=pack)

        from y5n.apps.yak.installer.installer import resolve_tool
        from y5n.apps.yak.resolver.install import find_artifact

        tool = resolve_tool(target)
        if tool is not None:
            return _Component(kind="tool", name=target, tool=tool)

        artifact = find_artifact(target, sources=sources)
        if artifact is not None:
            return _Component(kind="artifact", name=target, artifact=artifact)
        return None

    def _make_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
        force: bool,
        sources: list[str] | None,
    ) -> tuple[list, list] | None:
        """Make the component available in the installation's environment.

        Returns (all_packs, mounts) or None when nothing is new.
        """
        if component.kind == "pack":
            return self._make_pack_available(component, target, path, existing_packs)
        if component.kind == "tool":
            return self._make_tool_available(component, path, existing_packs)
        return self._make_artifact_available(
            component, target, path, existing_packs, force, sources
        )

    def _make_tool_available(
        self,
        component: _Component,
        path: Path,
        existing_packs: list,
    ) -> tuple[list, list] | None:
        """Install a host app (shell, web, ...) into the installation's venv."""
        tool = component.tool
        assert tool is not None
        if PackName(tool.name) in existing_packs:
            return None

        inst = Installation(
            name=tool.name,
            root=path.resolve(),
            packs=existing_packs + [PackName(tool.name)],
        )
        self._installer.install(inst, tools=[tool], sdk_path=self._sdk_path)
        return existing_packs + [PackName(tool.name)], []

    def _make_pack_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
    ) -> tuple[list, list] | None:
        pack = component.pack
        assert pack is not None
        # A pack is one unit; its mounts name the packs it depends on.
        packs = [PackName(m.source) for m in pack.mounts]
        if not packs:
            packs = [PackName(target)]
        added = [p for p in packs if p not in existing_packs]
        if not added:
            return None
        all_packs = existing_packs + added

        mounts = self.resolve_mount_sources(pack.mounts)
        if not mounts:
            artifact = self._artifacts.get_artifact(PackName(target))
            if artifact and (artifact / "structure").is_dir():
                target_path = pack.mount or f"/{target}"
                mounts = [
                    Mount(
                        source=str((artifact / "structure").resolve()),
                        target=target_path,
                    )
                ]

        inst = Installation(
            name=target,
            root=path.resolve(),
            packs=all_packs,
        )
        self._installer.install(inst, tools=pack.tools, sdk_path=self._sdk_path)
        return all_packs, mounts

    def _make_artifact_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
        force: bool,
        sources: list[str] | None,
    ) -> tuple[list, list] | None:
        if PackName(target) in existing_packs and not force:
            return None

        from y5n.apps.yak.resolver.install import install_artifact

        ok = install_artifact(target, target_root=path, force=force, sources=sources)
        if not ok:
            raise RuntimeError(f"Failed to install artifact: {target}")

        all_packs = existing_packs + [PackName(target)]

        mounts = self._artifact_mounts(component.artifact)
        return all_packs, mounts

    def _artifact_mounts(self, artifact) -> list:
        """The workspace mounts a meta-artifact declares, resolved."""
        from y5n.apps.yak.resolver.artifact import load_workspace_manifest

        if artifact is None or artifact.manifest is None:
            return []
        ws = load_workspace_manifest(artifact.manifest)
        if ws is None:
            return []
        return self.resolve_mount_sources(ws.mounts)

    # ── Update ──

    def update(
        self,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
    ) -> Installation:
        with self._step(ui, "Resolving"):
            from y5n.apps.yak.environment.io import load as load_env

            inst = self.load(path)
            if inst is None:
                raise ValueError(f"Installation not found: {path}")
            if inst.status == InstallationStatus.RUNNING:
                raise RuntimeError(f"Cannot update running installation: {inst.name}")
            env = load_env(path)
            if env is None:
                raise RuntimeError(f"No environment found at {path}")

        # Reconcile against the recorded desired state (the environment):
        # re-materialize its mounts, rediscover stores, reinstall.
        now = datetime.now(UTC)
        structure_dir = path / env.workspace_path
        with self._step(ui, "Workspace"):
            self._materializer.materialize(structure_dir, mounts=list(env.mounts))

        with self._step(ui, "Deployment"):
            # Preserve the operator's bindings; only newly declared stores
            # are (re)assembled.
            existing = load_installation(path / ".yak" / "deployment.yml")
            self._assemble(structure_dir, path / ".yak", existing=existing, asker=asker)

        inst.packs = list(env.dependencies)
        inst.status = InstallationStatus.MATERIALIZED
        inst.updated = now
        self._write_state(inst)

        with self._step(ui, "Installing"):
            self._installer.install(inst, sdk_path=self._sdk_path)

        with self._step(ui, "Environment"):
            touch(
                path,
                name=env.name,
                dependencies=list(env.dependencies),
                mounts=list(env.mounts),
            )

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
        pid = self.runtime_status(root)
        if pid is not None:
            issues.append(f"✓ Runtime       running (pid {pid})")
        elif (root / ".yak" / "runtime.pid").exists():
            issues.append("✘ Runtime       pid file stale — run 'yak runtime restart'")
        else:
            issues.append("— Runtime       not running")

        return issues

    # ── Run / Stop ──

    def run_runtime(self, path: Path) -> int | None:
        """Start the runtime service for a root; return the new pid.

        The process runs in the background via a venv wrapper script; the
        pid is recorded at ``.yak/runtime.pid``. Returns None when the
        runtime is already running.
        """
        pid_file = path / ".yak" / "runtime.pid"
        if self._read_pid(pid_file) is not None:
            return None

        log_dir = path / ".yak" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "runtime.log"

        venv_python = path / ".venv" / "bin" / "python"
        wrapper = path / ".venv" / "bin" / "yakoon-runtime"
        wrapper.write_text(
            f"#!{venv_python}\n"
            "import ctypes, ctypes.util\n"
            "libc = ctypes.CDLL(ctypes.util.find_library('c'))\n"
            "libc.prctl(15, b'yakoon-runtime', 0, 0, 0)\n"
            "from y5n.apps.runtime.__main__ import main\n"
            "main()\n"
        )
        wrapper.chmod(0o755)

        with open(log_file, "a") as lf:
            proc = subprocess.Popen([str(wrapper)], cwd=path, stdout=lf, stderr=lf)
        pid_file.write_text(str(proc.pid))
        self._mark_running(path, running=True)
        return proc.pid

    def stop_runtime(self, path: Path) -> int | None:
        """Stop the runtime service for a root; return the stopped pid."""
        pid_file = path / ".yak" / "runtime.pid"
        pid = self._read_pid(pid_file)
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        pid_file.unlink(missing_ok=True)
        self._mark_running(path, running=False)
        return pid

    def runtime_status(self, path: Path) -> int | None:
        """Return the running runtime pid for a root, or None."""
        return self._read_pid(path / ".yak" / "runtime.pid")

    @staticmethod
    def _read_pid(pid_file: Path) -> int | None:
        if not pid_file.exists():
            return None
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (OSError, ValueError):
            return None

    def _mark_running(self, path: Path, *, running: bool) -> None:
        inst = self.load(path)
        if inst is None:
            return
        inst.status = (
            InstallationStatus.RUNNING if running else InstallationStatus.STOPPED
        )
        inst.updated = datetime.now(UTC)
        self._write_state(inst)

    def load(self, path: Path) -> Installation | None:
        """Load an installation from an arbitrary path."""
        state_file = path / ".yak" / "state.toml"
        if not state_file.exists():
            return None
        return self._read_state(state_file)

    # ── Mount resolution ──

    def _platform_mounts(self) -> list:
        """The platform's structure namespaces: root at / and boot at /boot.

        Neither provides commands — root defines the tree root and its
        ``.yak/path`` command paths; boot is the Python host namespace.
        """
        from y5n.apps.yak.pack.models import Mount

        mounts: list = []
        if self._packs_root is not None:
            root_pack = self._packs_root / "y5n-packs-root"
            if (root_pack / "structure").is_dir():
                mounts.append(
                    Mount(source=str((root_pack / "structure").resolve()), target="/")
                )
        if self._runtime_root is not None:
            boot = self._runtime_root / "y5n-runtime-boot"
            if (boot / "structure").is_dir():
                mounts.append(
                    Mount(source=str((boot / "structure").resolve()), target="/boot")
                )
        return mounts

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
