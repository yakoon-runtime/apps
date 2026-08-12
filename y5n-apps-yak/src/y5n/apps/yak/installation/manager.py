from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
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
from y5n.apps.yak.installation.models import Component, Installation, InstallationStatus
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


@dataclass(frozen=True)
class RuntimeOccupant:
    """A process listening on a runtime's port."""

    pid: int
    yakoon: bool


RUNTIME_CONFIG_FILENAME = "yakoon-runtime.yml"
RUNTIME_DEFAULT_HOST = "127.0.0.1"
RUNTIME_DEFAULT_PORT = 9100
RUNTIME_START_TIMEOUT = 20.0

COMPONENTS_DIR = "components"


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
        workspace_path: str = "structure",
    ) -> Installation:
        """Install the minimal Yakoon platform into ``path``.

        The platform is the runtime, the SDK and the host apps only — no
        packs. What the installation can do is decided afterwards with
        ``yak add``. The platform's own namespaces (root, boot) are
        staged into ``.yak/components/`` and the workspace materializes
        exclusively from there. ``workspace_path`` is the workspace
        layout: ``structure/`` for a regular installation,
        ``workspace/structure/`` when bootstrapping inside a source
        checkout.
        """
        now = datetime.now(UTC)
        root = path.resolve()
        name = root.name or "yakoon"
        structure_dir = root / workspace_path
        with self._step(ui, "Workspace"):
            root.mkdir(parents=True, exist_ok=True)
            platform = self._platform_components(root)
            mounts = self._component_mounts(root, platform)
            self._materializer.materialize(
                structure_dir,
                mounts=mounts,
                components_dir=self._components_dir(root),
            )

        with self._step(ui, "Deployment"):
            self._assemble(structure_dir, root / ".yak", asker=asker)

        inst = Installation(
            name=name,
            root=root,
            packs=[PackName(c.name) for c in platform],
            components=platform,
            status=InstallationStatus.MATERIALIZED,
            created=now,
            updated=now,
        )
        self._write_state(inst)

        with self._step(ui, "Installing"):
            from y5n.apps.yak.installer.installer import PLATFORM_TOOLS

            self._installer.install(inst, tools=PLATFORM_TOOLS, sdk_path=self._sdk_path)

        with self._step(ui, "Environment"):
            touch(
                root,
                name=name,
                components=[PackName(c.name) for c in platform],
                mounts=mounts,
                workspace_path=workspace_path,
            )

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
        persist. Only "make available" differs — a pack is linked from
        its source, an artifact installs its payload and is copied.
        Returns None when the component is already part of the
        installation.
        """
        with self._step(ui, "Resolving"):
            from y5n.apps.yak.environment.io import load as load_env

            env = load_env(path)
            if env is None:
                raise RuntimeError(f"No installation found at {path}")
            existing = list(env.components)

            component = self._resolve_component(target, sources=sources)
            if component is None:
                raise ValueError(f"Unknown component: {target}")

        with self._step(ui, "Making available"):
            made = self._make_available(
                component, target, path, existing, force, sources
            )
            if made is None:
                return None
            all_packs, mounts, records = made

        structure_dir = path / env.workspace_path
        merged = list(env.mounts) + [m for m in mounts if m not in env.mounts]

        with self._step(ui, "Materializing"):
            self._materializer.materialize(
                structure_dir,
                mounts=merged,
                components_dir=self._components_dir(path),
            )

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
            components=(existing_inst.components if existing_inst else []) + records,
            status=InstallationStatus.MATERIALIZED,
            created=now,
            updated=now,
        )
        self._write_state(inst)

        with self._step(ui, "Environment"):
            touch(path, name=env.name, components=all_packs, mounts=merged)

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
    ) -> tuple[list, list, list] | None:
        """Make the component available in the installation's environment.

        Returns (all_packs, mounts, records) or None when nothing is new.
        The mounts always reference the staged component store
        (``.yak/components/<name>/structure``), never an artifact store
        or a language package.
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
    ) -> tuple[list, list, list] | None:
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
        records = [
            Component(name=tool.name, mode="tool", package=f"y5n-apps-{tool.name}")
        ]
        return existing_packs + [PackName(tool.name)], [], records

    def _make_pack_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
    ) -> tuple[list, list, list] | None:
        """Link a source pack into the installation (editable).

        The pack's structure is staged as a symlink under
        ``.yak/components/<name>/structure``; the workspace mounts from
        that staged path, so edits in the pack's source tree stay
        visible while the workspace never references the source directly.
        """
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

        records: list[Component] = []
        mounts: list[Mount] = []
        for name in added:
            pack_dir = self._repo.resolve_pack_dir(str(name))
            structure = (pack_dir / "structure") if pack_dir else None
            mount = (pack.mount or f"/{target}") if name == PackName(target) else ""
            if structure is not None and structure.is_dir():
                self._stage_structure(path, str(name), structure, copy=False)
                records.append(
                    Component(
                        name=str(name),
                        mode="source",
                        source=str(structure),
                        mount=mount,
                        package=f"y5n-packs-{name}",
                    )
                )
                if mount:
                    mounts.append(
                        Mount(
                            source=str(self._component_structure(path, str(name))),
                            target=mount,
                        )
                    )
            else:
                records.append(
                    Component(
                        name=str(name),
                        mode="source",
                        mount=mount,
                        package=f"y5n-packs-{name}",
                    )
                )

        inst = Installation(
            name=target,
            root=path.resolve(),
            packs=all_packs,
        )
        self._installer.install(inst, tools=pack.tools, sdk_path=self._sdk_path)
        return all_packs, mounts, records

    def _make_artifact_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
        force: bool,
        sources: list[str] | None,
    ) -> tuple[list, list, list] | None:
        if PackName(target) in existing_packs and not force:
            return None

        from y5n.apps.yak.resolver.install import install_artifact

        ok = install_artifact(target, target_root=path, force=force, sources=sources)
        if not ok:
            raise RuntimeError(f"Failed to install artifact: {target}")

        all_packs = existing_packs + [PackName(target)]
        records, mounts = self._stage_artifact(component.artifact, target, path)
        return all_packs, mounts, records

    def _stage_artifact(
        self, artifact, target: str, path: Path
    ) -> tuple[list[Component], list[Mount]]:
        """Stage an artifact into .yak/components and produce its mounts.

        A pack artifact copies its structure into the component store
        (self-contained: the installation works without the artifact
        store afterwards). A meta-artifact declares workspace mounts and
        contributes no namespace of its own.
        """
        if artifact is None:
            return [Component(name=target, mode="artifact")], []

        # A meta-artifact: its declared workspace mounts.
        if artifact.is_meta():
            from y5n.apps.yak.resolver.artifact import load_workspace_manifest

            mounts: list[Mount] = []
            if artifact.manifest is not None:
                ws = load_workspace_manifest(artifact.manifest)
                if ws is not None:
                    mounts = self.resolve_mount_sources(ws.mounts)
            return [
                Component(
                    name=target,
                    mode="artifact",
                    version=artifact.version,
                    fingerprint=artifact.fingerprint,
                )
            ], mounts

        # A pack artifact: copy its structure into the component store.
        mount = artifact.mount or f"/{target}"
        record = Component(
            name=target,
            mode="artifact",
            version=artifact.version,
            fingerprint=artifact.fingerprint,
            mount=mount,
            package=self._wheel_dist(artifact.package_file),
        )
        mounts = []
        if artifact.structure is not None:
            self._stage_structure(path, target, artifact.structure, copy=True)
            mounts = [
                Mount(
                    source=str(self._component_structure(path, target)),
                    target=mount,
                )
            ]
        return [record], mounts

    @staticmethod
    def _wheel_dist(package_file: Path | None) -> str:
        """The pip distribution name of a wheel file, if derivable."""
        if package_file is None:
            return ""
        dist = package_file.name.split("-", 1)[0]
        return dist.replace("_", "-")

    # ── Update ──

    def update(
        self,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
    ) -> Installation:
        """Reconcile the installation (IST) against the environment (SOLL).

        Desired components not yet installed are made available; installed
        components no longer desired are removed; artifact components whose
        fingerprint changed are re-staged. The workspace is then
        re-materialized from the staged component store only.
        """
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

        now = datetime.now(UTC)
        structure_dir = path / env.workspace_path
        desired = [str(c) for c in env.components]
        actual = [c.name for c in inst.components]
        merged = {c.name: c for c in inst.components}

        with self._step(ui, "Reconciling"):
            missing = [d for d in desired if d not in actual]
            obsolete = [a for a in actual if a not in desired]

            from y5n.apps.yak.resolver.install import find_artifact, install_artifact

            for name in missing:
                component = self._resolve_component(name)
                if component is None:
                    continue
                made = self._make_available(
                    component,
                    name,
                    path,
                    [PackName(n) for n in actual],
                    False,
                    None,
                )
                if made is None:
                    continue
                _, _, records = made
                for record in records:
                    merged[record.name] = record

            for name in obsolete:
                self._remove_component(path, name)
                merged.pop(name, None)

            for name in desired:
                record = merged.get(name)
                if record is None or record.mode != "artifact":
                    continue
                artifact = find_artifact(name)
                if artifact is None or artifact.is_meta():
                    continue
                if artifact.fingerprint and artifact.fingerprint != record.fingerprint:
                    install_artifact(name, target_root=path, force=True)
                    if artifact.structure is not None:
                        self._stage_structure(
                            path, name, artifact.structure, copy=True, replace=True
                        )
                    merged[name] = Component(
                        name=name,
                        mode="artifact",
                        version=artifact.version,
                        fingerprint=artifact.fingerprint,
                        mount=artifact.mount or record.mount,
                        package=self._wheel_dist(artifact.package_file),
                    )

        new_records = [merged.get(d, Component(name=d)) for d in desired]

        with self._step(ui, "Workspace"):
            self._materializer.materialize(
                structure_dir,
                mounts=list(env.mounts),
                components_dir=self._components_dir(path),
            )

        with self._step(ui, "Deployment"):
            # Preserve the operator's bindings; only newly declared stores
            # are (re)assembled.
            existing = load_installation(path / ".yak" / "deployment.yml")
            self._assemble(structure_dir, path / ".yak", existing=existing, asker=asker)

        inst.packs = [PackName(c.name) for c in new_records]
        inst.components = new_records
        inst.status = InstallationStatus.MATERIALIZED
        inst.updated = now
        self._write_state(inst)

        with self._step(ui, "Installing"):
            self._installer.install(inst, sdk_path=self._sdk_path)

        with self._step(ui, "Environment"):
            touch(
                path,
                name=env.name,
                components=list(env.components),
                mounts=list(env.mounts),
            )

        inst.status = InstallationStatus.CREATED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)
        return inst

    def _remove_component(self, path: Path, name: str) -> None:
        """Remove a component: drop its staged namespace and uninstall it."""
        comp_dir = self._components_dir(path) / name
        if comp_dir.exists():
            shutil.rmtree(comp_dir, ignore_errors=True)

        inst = self.load(path)
        if inst is None:
            return
        record = next((c for c in inst.components if c.name == name), None)
        if record is not None and record.package:
            python = path / ".venv" / "bin" / "python"
            if python.exists():
                subprocess.run(
                    [str(python), "-m", "pip", "uninstall", "-y", record.package],
                    capture_output=True,
                    check=False,
                )

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
                f"✓ Environment   {len(env.mounts)} mount(s), {len(env.components)} component(s)"
            )

        # Components from state
        if inst.components:
            for component in inst.components:
                structure = self._component_structure(root, component.name)
                if component.mode == "source" and component.source:
                    if structure.is_symlink() and not structure.exists():
                        issues.append(
                            f"✘ Component     {component.name}: source-link dangling "
                            f"({component.source})"
                        )
                    else:
                        issues.append(f"✓ Component     {component.name} (source)")
                elif component.mode == "artifact":
                    if structure.is_dir() and not structure.is_symlink():
                        issues.append(f"✓ Component     {component.name} (artifact)")
                    else:
                        issues.append(
                            f"✘ Component     {component.name}: staged structure missing"
                        )
                else:
                    issues.append(f"✓ Component     {component.name} (tool)")

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

    def run_runtime(
        self, path: Path, *, timeout: float = RUNTIME_START_TIMEOUT
    ) -> int | None:
        """Start the runtime service for a root; return the new pid.

        The process runs in the background via a venv wrapper script; the
        pid is recorded at ``.yak/runtime.pid``. Returns None when the
        runtime is already running. Raises RuntimeError when the runtime
        port is taken or the process does not become ready within
        ``timeout`` seconds — in both cases the start is aborted and no
        pid is recorded.
        """
        pid_file = path / ".yak" / "runtime.pid"
        if self._read_pid(pid_file) is not None:
            return None

        host, port = self._runtime_listen(path)

        occupants = self._holding_pids(port)
        if occupants or self._port_occupied(host, port):
            raise RuntimeError(self._collision_message(host, port, occupants))

        log_dir = path / ".yak" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "runtime.log"
        log_offset = log_file.stat().st_size if log_file.exists() else 0

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

        ready, tail = self._wait_ready(
            host, port, proc, log_file=log_file, offset=log_offset, timeout=timeout
        )
        if not ready:
            proc.terminate()
            pid_file.unlink(missing_ok=True)
            self._mark_running(path, running=False)
            raise RuntimeError(
                f"Runtime failed to start within {timeout:g}s (pid {proc.pid}).\n"
                f"{tail.strip() or 'No output yet.'}"
            )

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

    def runtime_occupant(self, path: Path) -> RuntimeOccupant | None:
        """The first process listening on the runtime's port, or None.

        Best-effort: an untracked listener (e.g. a stale runtime left
        over from another installation) is reported so the operator can
        release the port. Returns None when the port is free or the
        listener cannot be determined.
        """
        _, port = self._runtime_listen(path)
        for pid in self._holding_pids(port):
            return RuntimeOccupant(pid=pid, yakoon=self._is_yakoon_runtime(pid))
        return None

    # ── Runtime port / readiness helpers ──

    def _runtime_listen(self, path: Path) -> tuple[str, int]:
        """The address the runtime will listen on for a root.

        Mirrors the runtime app's config search: the first
        ``yakoon-runtime.yml`` found walking up from the root, then the
        user config, defaulting to the runtime default address.
        """
        for parent in [path, *path.parents]:
            cfg = parent / RUNTIME_CONFIG_FILENAME
            if cfg.is_file():
                return self._parse_listen_config(cfg)
        user_cfg = Path.home() / ".config" / "y5n" / RUNTIME_CONFIG_FILENAME
        if user_cfg.is_file():
            return self._parse_listen_config(user_cfg)
        return (RUNTIME_DEFAULT_HOST, RUNTIME_DEFAULT_PORT)

    @staticmethod
    def _parse_listen_config(cfg: Path) -> tuple[str, int]:
        try:
            data = yaml.safe_load(cfg.read_text()) or {}
        except OSError:
            return (RUNTIME_DEFAULT_HOST, RUNTIME_DEFAULT_PORT)
        listen = data.get("listen") or {}
        host = listen.get("host", RUNTIME_DEFAULT_HOST)
        try:
            port = int(listen.get("port", RUNTIME_DEFAULT_PORT))
        except (TypeError, ValueError):
            port = RUNTIME_DEFAULT_PORT
        return (str(host), port)

    def _port_occupied(self, host: str, port: int) -> bool:
        """Whether a socket is already listening on the address."""
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return False
        except OSError:
            return True
        finally:
            sock.close()

    def _holding_pids(self, port: int) -> list[int]:
        """Pids listening on ``port`` (Linux /proc, best-effort)."""
        inodes: set[str] = set()
        for table in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                with open(table) as f:
                    next(f)
                    for line in f:
                        parts = line.split()
                        if len(parts) < 10 or parts[3] != "0A":
                            continue
                        hexport = parts[1].rpartition(":")[2]
                        try:
                            if int(hexport, 16) != port:
                                continue
                        except ValueError:
                            continue
                        inodes.add(parts[9])
            except OSError:
                continue

        pids: list[int] = []
        for pid in self._iter_pids():
            try:
                fd_dir = Path(f"/proc/{pid}/fd")
                for fd in fd_dir.iterdir():
                    try:
                        target = os.readlink(fd)
                    except OSError:
                        continue
                    if target.startswith("socket:["):
                        if target[len("socket:[") : -1] in inodes:
                            pids.append(pid)
                            break
            except OSError:
                continue
        return pids

    @staticmethod
    def _iter_pids() -> list[int]:
        try:
            return [int(e.name) for e in Path("/proc").iterdir() if e.name.isdigit()]
        except OSError:
            return []

    @staticmethod
    def _is_yakoon_runtime(pid: int) -> bool:
        try:
            cmdline = (Path(f"/proc/{pid}/cmdline").read_bytes() or b"").decode(
                errors="replace"
            )
        except OSError:
            return False
        return "yakoon-runtime" in cmdline

    def _collision_message(self, host: str, port: int, occupants: list[int]) -> str:
        if occupants:
            holder = ", ".join(
                f"pid {p}" + (" (yakoon-runtime)" if self._is_yakoon_runtime(p) else "")
                for p in occupants
            )
            return (
                f"Port {host}:{port} is already in use by {holder}.\n"
                "If it is a stale runtime, stop it first — e.g. 'yak runtime stop' "
                "from its installation or 'kill <pid>'."
            )
        return (
            f"Port {host}:{port} is already in use by another process.\n"
            "Free the port and try again."
        )

    def _wait_ready(
        self,
        host: str,
        port: int,
        proc,
        *,
        log_file: Path,
        offset: int,
        timeout: float,
    ) -> tuple[bool, str]:
        """Poll until the runtime accepts connections or the process dies.

        Returns (ready, log_tail). Readiness means the socket accepts a
        TCP connection — the WebSocket server is actually listening, not
        merely spawned. ``offset`` limits the log tail to what the new
        process has written.
        """
        deadline = time.monotonic() + timeout
        while True:
            if self._can_connect(host, port):
                return True, self._read_log_tail(log_file, offset)
            if proc.poll() is not None:
                return False, self._read_log_tail(log_file, offset)
            if time.monotonic() >= deadline:
                return False, self._read_log_tail(log_file, offset)
            time.sleep(0.1)

    @staticmethod
    def _can_connect(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            return False

    @staticmethod
    def _read_log_tail(log_file: Path, offset: int) -> str:
        try:
            with open(log_file, errors="replace") as f:
                f.seek(offset)
                return "\n".join(f.read().splitlines()[-10:])
        except OSError:
            return ""

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

    # ── Component store / mount resolution ──

    def _components_dir(self, path: Path) -> Path:
        """The installation-local component store: ``.yak/components``."""
        return path / ".yak" / COMPONENTS_DIR

    def _component_structure(self, path: Path, name: str) -> Path:
        """The canonical namespace path of one installed component."""
        return self._components_dir(path) / name / "structure"

    def _stage_structure(
        self,
        path: Path,
        name: str,
        source_dir: Path,
        *,
        copy: bool,
        replace: bool = False,
    ) -> Path:
        """Stage a component's namespace into ``.yak/components/<name>/structure``.

        Source components are symlinked (editable — the workspace never
        points at the source directly, only through the staged path).
        Artifact components are copied (self-contained — the installation
        works without the artifact store afterwards). ``replace`` re-stages
        an existing copy (used when an artifact component is updated).
        """
        target = self._component_structure(path, name)
        if target.exists() and replace:
            shutil.rmtree(target, ignore_errors=True)
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copytree(source_dir, target)
        else:
            target.symlink_to(source_dir.absolute(), target_is_directory=True)
        return target

    def _platform_components(self, path: Path) -> list[Component]:
        """The platform's own namespace components: root at / and boot at /boot.

        Neither provides commands — root defines the tree root and its
        ``.yak/path`` command paths; boot is the Python host namespace.
        Both are staged into the component store like any other component.
        """
        components: list[Component] = []
        if self._packs_root is not None:
            root_src = self._packs_root / "y5n-packs-root" / "structure"
            if root_src.is_dir():
                self._stage_structure(path, "root", root_src, copy=False)
                components.append(
                    Component(
                        name="root", mode="source", source=str(root_src), mount="/"
                    )
                )
        if self._runtime_root is not None:
            boot_src = self._runtime_root / "y5n-runtime-boot" / "structure"
            if boot_src.is_dir():
                self._stage_structure(path, "boot", boot_src, copy=False)
                components.append(
                    Component(
                        name="boot", mode="source", source=str(boot_src), mount="/boot"
                    )
                )
        return components

    def _component_mounts(self, path: Path, components: list[Component]) -> list:
        """The mounts a set of components materializes in the workspace."""
        from y5n.apps.yak.pack.models import Mount

        return [
            Mount(
                source=str(self._component_structure(path, c.name)),
                target=c.mount,
            )
            for c in components
            if c.mount and self._component_structure(path, c.name).exists()
        ]

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
        packs_toml = ", ".join(f'"{p}"' for p in inst.packs)
        lines = [
            "[installation]",
            f'name = "{inst.name}"',
            f'status = "{inst.status.value}"',
            f"packs = [{packs_toml}]",
            f'created = "{inst.created.isoformat() if inst.created else ""}"',
            f'updated = "{inst.updated.isoformat() if inst.updated else ""}"',
            "",
        ]
        for component in inst.components:
            lines.append("[[components]]")
            lines.append(f'name = "{component.name}"')
            lines.append(f'mode = "{component.mode}"')
            if component.source:
                lines.append(f'source = "{component.source}"')
            if component.version:
                lines.append(f'version = "{component.version}"')
            if component.fingerprint:
                lines.append(f'fingerprint = "{component.fingerprint}"')
            if component.mount:
                lines.append(f'mount = "{component.mount}"')
            if component.package:
                lines.append(f'package = "{component.package}"')
            lines.append("")
        (state_dir / "state.toml").write_text("\n".join(lines))

    def _read_state(self, path: Path) -> Installation | None:
        import tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)
        inst_data = data.get("installation", {})
        if not inst_data:
            return None
        components = []
        for raw in data.get("components", []):
            components.append(
                Component(
                    name=raw.get("name", ""),
                    mode=raw.get("mode", "source"),
                    source=raw.get("source", ""),
                    version=raw.get("version", ""),
                    fingerprint=raw.get("fingerprint", ""),
                    mount=raw.get("mount", ""),
                    package=raw.get("package", ""),
                )
            )
        return Installation(
            name=inst_data.get("name", ""),
            root=path.parent.parent,
            packs=[PackName(p) for p in inst_data.get("packs", [])],
            components=components,
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
