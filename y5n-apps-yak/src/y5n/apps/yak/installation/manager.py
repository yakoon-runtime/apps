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
from y5n.apps.yak.installation.deployment import (
    Installation as RuntimeInstallation,
)
from y5n.apps.yak.installation.deployment import load_installation, to_dict
from y5n.apps.yak.installation.models import Component, Installation, InstallationStatus
from y5n.apps.yak.installer.installer import Installer
from y5n.apps.yak.pack.models import Mount, Pack, PackName
from y5n.apps.yak.repository.artifact import ArtifactStore
from y5n.apps.yak.repository.interface import Repository
from y5n.apps.yak.resolver.artifact import Artifact
from y5n.apps.yak.workspace.materializer import Materializer


@dataclass(frozen=True)
class _Component:
    """A resolved installable: a source component, a pack or an artifact.
    ``source`` is the structure directory of an explicitly mapped
    development source (ADR-8)."""

    kind: str
    name: str
    pack: Pack | None = None
    artifact: Artifact | None = None
    source: Path | None = None


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
        runtime_root: Path | None = None,
        context=None,
    ) -> None:
        self._repo = repository
        self._artifacts = artifact_store
        self._materializer = Materializer()
        self._installer = Installer(artifact_store, runtime_root=runtime_root)
        self._sdk_path = sdk_path
        self._runtime_root = runtime_root
        self._context = context
        self._index_cache = None

    def _index(self):
        """The merged source index (ADR-20), built from the Context sources."""
        if self._index_cache is None:
            if self._context is not None and self._context.sources:
                from y5n.apps.yak.resolver.catalog import build_index

                self._index_cache = build_index(
                    self._context.sources, self._context.path
                )
            else:
                from y5n.apps.yak.resolver.catalog import Index

                self._index_cache = Index()
        return self._index_cache

    # ── Install ──

    def install(
        self,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
        workspace_path: str = "structure",
    ) -> Installation:
        """Materialize the environment the Context points at (ADR-8).

        ``install`` reads the Context's ``environment`` reference, resolves
        the manifest through the repositories and materializes every
        declared component — root and boot included, with no special
        status. Without a resolvable environment it falls back to the
        minimal platform namespaces (transition). ``workspace_path`` is
        the workspace layout: ``structure/`` for a regular installation,
        ``workspace/structure/`` when bootstrapping inside a source
        checkout.
        """
        now = datetime.now(UTC)
        root = path.resolve()
        name = root.name or "yakoon"
        structure_dir = root / workspace_path
        with self._step(ui, "Workspace"):
            root.mkdir(parents=True, exist_ok=True)
            manifest = self._resolve_install_environment()
            platform = (
                self._materialize_environment(root, manifest)
                if manifest is not None
                else []
            )
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
            self._installer.install(inst, sdk_path=self._sdk_path)

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

    def _resolve_install_environment(self):
        """Resolve the Context's environment reference through the index."""
        if self._context is None or not self._context.environment:
            return None
        hit = self._index().resolve_environment(self._context.environment)
        if hit is None:
            return None
        catalog, location = hit
        from y5n.apps.yak.resolver.artifact import load_remote_environment

        path = self._materialize_location(catalog, location)
        if path is None:
            return None
        return load_remote_environment(path)

    def _install_artifact(self, artifact, path: Path, *, force: bool = False) -> bool:
        """Install a resolved artifact's wheel into the installation venv."""
        from y5n.apps.yak.installer.venv import ensure_venv

        wheel = artifact.package_file
        if wheel is None or not wheel.exists():
            return True
        python = ensure_venv(path / ".venv")
        cmd = [str(python), "-m", "pip", "install"]
        if force:
            cmd.append("--force-reinstall")
        cmd.append(str(wheel))
        import subprocess

        return subprocess.run(cmd, capture_output=True).returncode == 0

    def _materialize_environment(self, path: Path, manifest) -> list[Component]:
        """Reconcile a manifest into staged components (ADR-8).

        Yak knows no component names: every entry of the manifest is
        resolved through the source index, its wheel (if any) is
        installed, and its namespace staged — exactly like any component
        added later with ``yak add``.
        """
        components: list[Component] = []
        for name in manifest.components:
            comp = self._resolve_component(str(name))
            if comp is None:
                continue
            if comp.kind == "artifact" and comp.artifact is not None:
                self._install_artifact(comp.artifact, path)
            components.append(self._ensure_component(path, str(name), comp))
        return components

    # ── Add ──

    def add(
        self,
        target: str,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
        sources: list[str] | None = None,
        sources_exclusive: bool = False,
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

            component = self._resolve_component(
                target, sources=sources, sources_exclusive=sources_exclusive
            )
            if component is None:
                raise ValueError(f"Unknown component: {target}")

        records: list[Component] = []
        try:
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
                existing_dep = load_installation(path / ".yak" / "deployment.yml")
                self._assemble(
                    structure_dir, path / ".yak", existing=existing_dep, asker=asker
                )

            existing_inst = self.load(path)
            now = datetime.now(UTC)
            inst = Installation(
                name=existing_inst.name if existing_inst else target,
                root=path.resolve(),
                packs=all_packs,
                components=self._merge_component_records(
                    (existing_inst.components if existing_inst else []), records
                ),
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
        except Exception:
            # The operation failed after components were staged: roll back
            # the partial staging/payload so no residue remains.
            for record in records:
                self._cleanup_component(path, record)
            raise

    def _resolve_component(
        self,
        target: str,
        *,
        sources: list[str] | None = None,
        sources_exclusive: bool = False,
        naming: bool = True,
    ) -> _Component | None:
        """Resolve a component through the source index (ADR-20).

        ``index.resolve(name)`` returns the first exact hit in source
        order; the located resource becomes a source pack or an artifact.
        There is no search, no name interpretation, and no fallback: an
        unknown identity resolves to nothing.
        """
        hit = self._index().resolve(target)
        if hit is None:
            return None
        catalog, ref = hit
        return self._component_from_ref(target, catalog, ref)

    def _component_from_ref(self, name: str, catalog, ref) -> _Component | None:
        """Materialize a catalog entry into a source pack or an artifact.

        The located resource decides its own kind by its metadata
        (``pack.toml`` → source pack, ``artifact.yml`` → artifact). The
        catalog's declared identity must equal the component's own
        identity — otherwise the load is an error.
        """
        from y5n.apps.yak.resolver.catalog import CatalogIdentityError

        resource = self._materialize_location(catalog, ref.location)
        if resource is None:
            return None
        pack = self._read_pack(resource)
        if pack is not None:
            if pack.name != name:
                raise CatalogIdentityError(
                    f"catalog declares '{name}' but the component is "
                    f"'{pack.name}' at {resource}"
                )
            structure = resource / "structure"
            source = structure if structure.is_dir() else resource
            return _Component(
                kind="pack",
                name=pack.name,
                pack=Pack(name=pack.name, version=pack.version, mount=pack.mount),
                source=source,
            )
        artifact = self._parse_artifact(resource)
        if artifact is not None:
            if artifact.name != name:
                raise CatalogIdentityError(
                    f"catalog declares '{name}' but the artifact is "
                    f"'{artifact.name}' at {resource}"
                )
            return _Component(kind="artifact", name=name, artifact=artifact)
        return None

    def _materialize_location(self, catalog, location: str) -> Path | None:
        """Resolve a source-relative catalog location to a local resource."""
        if catalog.base is not None:
            path = catalog.base / location
            return path if path.exists() else None
        from y5n.apps.yak.resolver.catalog import CatalogError

        raise CatalogError(
            f"remote source '{catalog.spec}' materialization is not "
            f"implemented yet (local sources only)"
        )

    @staticmethod
    def _parse_artifact(resource: Path):
        """Build an Artifact from a resolved ``artifact.yml`` directory."""
        from y5n.apps.yak.resolver.artifact import (
            Artifact,
            _parse_manifest,
        )

        manifest = resource / "artifact.yml"
        if not manifest.exists():
            return None
        meta = _parse_manifest(manifest)
        if meta is None:
            return None
        fp = meta.get("fingerprint", "")
        if fp.startswith("sha256:"):
            fp = fp[7:]
        return Artifact(
            name=meta.get("name", ""),
            version=meta.get("version", "0"),
            kind=meta.get("kind", "package"),
            host=meta.get("host", "python"),
            builder=meta.get("builder", "python"),
            dependencies=meta.get("dependencies", []),
            fingerprint=fp,
            path=resource,
            mount=meta.get("mount"),
        )

    # ── Context source mapping (removed in ADR-20; sources replace it) ──

    @staticmethod
    def _read_pack(path: Path) -> Pack | None:
        """Read a component's own identity from its pack.toml, if any."""
        manifest = path / "pack.toml"
        if not manifest.exists():
            return None
        import tomllib

        with open(manifest, "rb") as f:
            data = tomllib.load(f)
        return Pack(
            name=data.get("name", path.name),
            version=data.get("version", "0.1"),
            mount=data.get("mount"),
        )

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
        Staging goes through ``_ensure_component`` so ``add`` and
        ``update`` share the same mechanism; on failure any partially
        staged components are cleaned up before re-raising.
        """
        if component.kind == "pack":
            return self._make_pack_available(
                component, target, path, existing_packs, force
            )
        return self._make_artifact_available(
            component, target, path, existing_packs, force, sources
        )

    def _make_pack_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
        force: bool,
    ) -> tuple[list, list, list] | None:
        """Link a source pack into the installation (editable)."""
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
        try:
            for name in added:
                if str(name) == target:
                    comp = component
                else:
                    comp = self._resolve_component(str(name)) or _Component(
                        kind="pack",
                        name=str(name),
                        pack=Pack(name=str(name), version="0.1"),
                    )
                record = self._ensure_component(path, str(name), comp, force=force)
                records.append(record)
                staged = self._component_structure(path, str(name))
                if record.mount and staged.exists():
                    mounts.append(Mount(source=str(staged), target=record.mount))

            inst = Installation(
                name=target,
                root=path.resolve(),
                packs=all_packs,
            )
            self._installer.install(inst, sdk_path=self._sdk_path)
        except Exception:
            for record in records:
                self._cleanup_component(path, record)
            raise
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

        if component.artifact is not None:
            ok = self._install_artifact(component.artifact, path, force=force)
            if not ok:
                raise RuntimeError(f"Failed to install artifact: {target}")

        all_packs = existing_packs + [PackName(target)]
        record = self._ensure_component(path, target, component, force=force)
        mounts: list[Mount] = []
        artifact = component.artifact
        if artifact is not None and artifact.is_meta():
            # A meta-artifact declares workspace mounts and contributes
            # no namespace of its own.
            from y5n.apps.yak.resolver.artifact import load_workspace_manifest

            if artifact.manifest is not None:
                ws = load_workspace_manifest(artifact.manifest)
                if ws is not None:
                    mounts = self.resolve_mount_sources(ws.mounts)
        else:
            staged = self._component_structure(path, target)
            if record.mount and staged.exists():
                mounts.append(Mount(source=str(staged), target=record.mount))
        return all_packs, mounts, [record]

    def _ensure_component(
        self,
        path: Path,
        name: str,
        component: _Component,
        *,
        force: bool = False,
    ) -> Component:
        """Stage ``.yak/components/<name>`` to match the resolved component.

        Source components become a symlink (editable), artifact components
        a local copy (self-contained). The staged object is replaced when
        it is missing, of the wrong kind (mode change) or ``force`` is
        set. Returns the IST ``Component`` record.
        """
        staged = self._component_structure(path, name)

        if component.kind == "pack":
            pack = component.pack
            mount = (pack.mount or f"/{name}") if pack is not None else f"/{name}"
            record = Component(
                name=name,
                mode="source",
                mount=mount,
                package=name,
            )
            source = component.source or self._pack_structure(name)
            if source is not None and source.is_dir():
                replace = force or self._staging_mismatch(staged, mode="source")
                self._stage_structure(path, name, source, copy=False, replace=replace)
                return Component(
                    name=name,
                    mode="source",
                    source=str(source),
                    mount=mount,
                    package=record.package,
                )
            return record

        artifact = component.artifact
        if artifact is None:
            return Component(name=name, mode="artifact")
        record = Component(
            name=name,
            mode="artifact",
            version=artifact.version,
            fingerprint=artifact.fingerprint,
            mount=artifact.mount or f"/{name}",
            package=self._wheel_dist(artifact.package_file),
        )
        if not artifact.is_meta() and artifact.structure is not None:
            replace = force or self._staging_mismatch(staged, mode="artifact")
            self._stage_structure(
                path, name, artifact.structure, copy=True, replace=replace
            )
        return record

    def _pack_structure(self, name: str) -> Path | None:
        """The structure dir of a source-pack component."""
        pack_dir = self._repo.resolve_pack_dir(name)
        if pack_dir is not None:
            src = pack_dir / "structure"
            if src.is_dir():
                return src
        return None

    @staticmethod
    def _staging_mismatch(staged: Path, *, mode: str) -> bool:
        """Whether the staged structure does not match the desired mode."""
        if mode == "source":
            return not (staged.is_symlink() and staged.exists())
        return not (staged.is_dir() and not staged.is_symlink())

    @staticmethod
    def _record_mode(component: _Component) -> str:
        return {"pack": "source", "artifact": "artifact"}[component.kind]

    def _cleanup_component(self, path: Path, record: Component) -> None:
        """Remove a component's staged namespace and installed payload."""
        comp_dir = self._components_dir(path) / record.name
        if comp_dir.exists():
            shutil.rmtree(comp_dir, ignore_errors=True)
        if record.package:
            python = path / ".venv" / "bin" / "python"
            if python.exists():
                subprocess.run(
                    [str(python), "-m", "pip", "uninstall", "-y", record.package],
                    capture_output=True,
                    check=False,
                )

    @staticmethod
    def _merge_component_records(
        existing: list[Component], added: list[Component]
    ) -> list[Component]:
        """Merge IST records — exactly one per component name."""
        by_name = {c.name: c for c in existing}
        for record in added:
            by_name[record.name] = record
        return list(by_name.values())

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
        merged = {c.name: c for c in inst.components}

        with self._step(ui, "Reconciling"):
            for name in desired:
                component = self._resolve_component(name)
                if component is None:
                    continue
                record = merged.get(name)
                fingerprint_drift = (
                    record is not None
                    and component.kind == "artifact"
                    and component.artifact is not None
                    and component.artifact.fingerprint
                    and component.artifact.fingerprint != record.fingerprint
                )
                mode_drift = (
                    record is not None and self._record_mode(component) != record.mode
                )
                if record is None or fingerprint_drift or mode_drift:
                    if fingerprint_drift and component.artifact is not None:
                        self._install_artifact(component.artifact, path, force=True)
                    merged[name] = self._ensure_component(
                        path, name, component, force=True
                    )
                else:
                    # Heals a missing/broken staged structure; a no-op when
                    # the staged component already matches the desired state.
                    merged[name] = self._ensure_component(path, name, component)

            obsolete = [name for name in merged if name not in desired]
            for name in obsolete:
                self._remove_component(path, name)
                merged.pop(name, None)

            self._remove_orphans(path, set(desired))

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
        inst = self.load(path)
        record = (
            next((c for c in inst.components if c.name == name), None)
            if inst is not None
            else None
        )
        self._cleanup_component(path, record or Component(name=name))

    def _remove_orphans(self, path: Path, desired: set[str]) -> None:
        """Remove staged components that are not desired (not in SOLL)."""
        comps = self._components_dir(path)
        if not comps.is_dir():
            return
        for entry in comps.iterdir():
            if entry.name not in desired and entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)

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
                    issues.append(f"✓ Component     {component.name}")

        # Orphans: staged components that are not desired (SOLL).
        if env:
            desired = {str(c) for c in env.components}
            comps_dir = self._components_dir(root)
            if comps_dir.is_dir():
                for entry in sorted(comps_dir.iterdir()):
                    if entry.name not in desired and entry.is_dir():
                        issues.append(
                            f"✘ Orphan        .yak/components/{entry.name} — "
                            "not in environment (run 'yak update')"
                        )

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
                    issues.append(f"✘ Fingerprint   {pack} outdated — run 'yak update'")

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
        an existing object — including a mode change between symlink and
        directory (used when an artifact component is updated or a
        component switches between source and artifact).
        """
        target = self._component_structure(path, name)
        if replace and (target.exists() or target.is_symlink()):
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copytree(source_dir, target)
        else:
            target.symlink_to(source_dir.absolute(), target_is_directory=True)
        return target

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
