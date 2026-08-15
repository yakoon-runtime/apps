from __future__ import annotations

import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import tomllib
import yaml
from y5n.apps.yak.environment.io import load as load_env
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
from y5n.apps.yak.installer.installer import Installer, PythonCandidate
from y5n.apps.yak.pack.models import Mount, Pack, PackName, read_mount
from y5n.apps.yak.repository.artifact import ArtifactStore
from y5n.apps.yak.repository.interface import Repository
from y5n.apps.yak.resolver.artifact import (
    Artifact,
    _parse_manifest,
)
from y5n.apps.yak.resolver.catalog import (
    CatalogError,
    CatalogIdentityError,
    Index,
    build_index,
    fetch_github_artifact,
    fetch_github_release,
)
from y5n.apps.yak.workspace.materializer import Materializer


@dataclass(frozen=True)
class _Component:
    """A resolved installable.

    ``source`` is the local resource resolved from the catalog (a
    checkout, pack or library); ``artifact`` is a fetched released
    artifact. Exactly one of them is set. ``mode`` mirrors which one:
    ``"source"`` or ``"artifact"``. ``structure`` is the optional
    ``<source>/structure`` contribution — the only part that is ever
    materialized into the workspace tree.
    """

    name: str
    mode: str
    pack: Pack | None = None
    artifact: Artifact | None = None
    source: Path | None = None
    structure: Path | None = None


COMPONENTS_DIR = "components"


class InstallationManager:
    def __init__(
        self,
        repository: Repository,
        artifact_store: ArtifactStore,
        *,
        context=None,
    ) -> None:
        self._repo = repository
        self._artifacts = artifact_store
        self._materializer = Materializer()
        self._installer = Installer()
        self._context = context
        self._index_cache = None
        from y5n.apps.yak.runtime.service import RuntimeService

        self.runtime = RuntimeService(mark_running=self._mark_running)

    def _index(self):
        """The merged source index (ADR-20), built from the Context sources."""
        if self._index_cache is None:
            ctx = self._current_context()
            if ctx is not None and ctx.sources:
                self._index_cache = build_index(ctx.sources, ctx.path)
            else:
                self._index_cache = Index()
        return self._index_cache

    def _current_context(self):
        """The Context, loaded lazily.

        ``yak install`` creates the context during the command; the
        manager may have been built just before that. Loading on first
        use lets a fresh install pick up its own init.
        """
        if self._context is None:
            from y5n.apps.yak.hosts.cli.cwd import Context

            self._context = Context.current()
        return self._context

    def _paths_index(self, paths) -> Index | None:
        """The preferred local index built from the ``--path`` catalogs.

        None when no ``--path`` was given. This index is preferred, not
        exclusive: a component found here resolves as a source; one that
        is absent still resolves through the Context index.
        """
        if not paths:
            return None
        ctx = self._current_context()
        context_root = ctx.path if ctx is not None else Path.cwd()
        return build_index([str(p) for p in paths], context_root)

    def _combined_index(self, paths=None) -> Index:
        """The identity lookup index: ``--path`` catalogs, then Context.

        A target (component or bundle) is looked up here — first hit wins,
        so ``--path`` catalogs precede the Context sources. The per-
        component resolution later decides source vs artifact.
        """
        if not paths:
            return self._index()
        ctx = self._current_context()
        context_root = ctx.path if ctx is not None else Path.cwd()
        sources = [str(p) for p in paths] + list(ctx.sources or [])
        return build_index(sources, context_root)

    def _resolve_preferred(self, target: str, *, paths_index=None, mode: str = "artifact"):
        """Resolve a component: ``--path`` source first, release otherwise.

        A component in any ``--path`` catalog uses its ``location`` (a
        local source); everything else resolves through the Context index
        using its ``release``. There is no global mode — the decision is
        per component. ``mode`` is only the release fallback for resolving
        a source pack's declared dependencies.
        """
        if paths_index is not None:
            hit = paths_index.resolve(target)
            if hit is not None:
                catalog, ref = hit
                return self._component_from_ref(target, catalog, ref, mode="source")
        return self._resolve_component(target, mode=mode)

    # ── Install ──

    def install(
        self,
        path: Path,
        *,
        identity: str,
        paths: list[str] | None = None,
        asker: StoreAsker | None = None,
        ui=None,
        workspace_path: str = "structure",
    ) -> Installation | None:
        """Make an identity part of an environment (ADR-21).

        The first argument of ``yak install`` is always an identity: a
        component or a bundle name. ``identity`` is that name. A bundle
        resolves to its members through the shared index; every member
        resolves like any other component.

        ``paths`` are repeatable ``--path`` catalogs: a component found in
        any of them resolves through its ``location`` (source); everything
        else resolves through its ``release`` (artifact) — per component,
        no global mode.

        On a fresh environment the identity is materialized from scratch;
        on an existing environment its components are added. Returns None
        when the identity is already part of the environment.
        """
        root = path.resolve()
        if load_env(root) is not None:
            index = self._combined_index(paths)
            added_any = False
            for name in self._identities(identity, index=index):
                if (
                    self._add_component(
                        str(name), root, asker=asker, ui=ui, paths=paths
                    )
                    is not None
                ):
                    added_any = True
            if not added_any:
                return None
            return self.load(root)

        now = datetime.now(UTC)
        name = root.name or "yakoon"
        structure_dir = root / workspace_path
        with self._step(ui, "Workspace"):
            root.mkdir(parents=True, exist_ok=True)
            staged = self._materialize_install(root, identity=identity, paths=paths)
            records = [r for r, _ in staged]
            resolved = [c for _, c in staged]
            mounts = self._component_mounts(root, records)
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
            packs=[PackName(c.name) for c in records],
            components=records,
            status=InstallationStatus.MATERIALIZED,
            created=now,
            updated=now,
        )
        self._write_state(inst)

        with self._step(ui, "Installing"):
            self._installer.install(root, self._python_candidates(resolved))

        with self._step(ui, "Environment"):
            touch(
                root,
                name=name,
                components=[PackName(c.name) for c in records],
                mounts=mounts,
                workspace_path=workspace_path,
            )

        inst.status = InstallationStatus.CREATED
        inst.updated = datetime.now(UTC)
        self._write_state(inst)
        return inst

    def _materialize_install(
        self,
        path: Path,
        *,
        identity: str,
        paths: list[str] | None = None,
    ) -> list[tuple[Component, _Component]]:
        """Resolve and stage the identity's components.

        The identity names the components to compose (a bundle's members,
        or the single component). Each is resolved per component: source
        from any ``--path`` catalog, release otherwise, then staged into
        the component store. Returns (record, resolved) pairs — the staged
        IST record and the resolved component that builds the Python
        install plan.
        """
        index = self._combined_index(paths)
        paths_index = self._paths_index(paths)
        staged: list[tuple[Component, _Component]] = []
        for name in self._identities(identity, index=index):
            comp = self._resolve_preferred(str(name), paths_index=paths_index)
            if comp is None:
                continue
            record = self._ensure_component(path, str(name), comp)
            staged.append((record, comp))
        return staged

    @staticmethod
    def _python_candidates(resolved: list[_Component]) -> list[PythonCandidate]:
        """The Python install plan: wheels for artifacts, editable for sources.

        Source and artifact are different origins of the same component;
        pip receives both forms in one transaction and resolves the whole
        graph at once. Yak knows no Python dependencies.
        """
        candidates: list[PythonCandidate] = []
        for comp in resolved:
            if comp.mode == "artifact" and comp.artifact is not None:
                wheel = comp.artifact.package_file
                if wheel is not None and wheel.exists():
                    candidates.append(PythonCandidate(wheel=wheel))
            elif comp.mode == "source" and comp.source is not None:
                candidates.append(PythonCandidate(project=comp.source))
        return candidates

    def _identities(
        self, identity: str, *, index: Index | None = None
    ) -> list[str]:
        """The component names an identity composes (bundle → members)."""
        index = index or self._index()
        bundle = index.resolve_bundle(identity)
        if bundle is not None:
            return list(bundle[1])
        if index.resolve(identity) is not None:
            return [identity]
        raise ValueError(f"Unknown identity: {identity}")

    def _bundle_members(self, identity: str) -> list[str]:
        """A bundle expands to its component names; anything else is itself.

        The public lifecycle identity is a bundle; a plain name passes
        through unchanged so the existing per-component commands keep
        working. Unlike ``_identities`` this never raises — an unknown
        name is left to the command's own resolution.
        """
        hit = self._index().resolve_bundle(identity)
        return list(hit[1]) if hit is not None else [identity]

    # ── Add (ADR-21: folded into install) ──

    def _add_component(
        self,
        target: str,
        path: Path,
        *,
        asker: StoreAsker | None = None,
        ui=None,
        force: bool = False,
        paths: list[str] | None = None,
    ) -> Installation | None:
        """Make one component part of an existing environment (ADR-21).

        The reconciliation is: resolve → make available → materialize →
        discover requirements → reconcile deployment → persist. ``paths``
        are repeatable ``--path`` catalogs: a component found in any of
        them resolves through its ``location`` (source); everything else
        through its ``release`` (artifact) — per component, no global
        mode. Returns None when the component is already part of the
        installation.
        """
        paths_index = self._paths_index(paths)

        with self._step(ui, "Resolving"):
            env = load_env(path)
            if env is None:
                raise RuntimeError(f"No installation found at {path}")
            existing = list(env.components)

            component = self._resolve_preferred(target, paths_index=paths_index)
            if component is None:
                raise ValueError(f"Unknown component: {target}")

            # A component already installed in a different mode is re-staged
            # in the new mode — the decision is per component (ADR-21).
            force = force or self._mode_changed(path, target, component.mode)

        records: list[Component] = []
        try:
            with self._step(ui, "Making available"):
                made = self._make_available(
                    component, target, path, existing, force, paths_index=paths_index
                )
                if made is None:
                    return None
                all_packs, mounts, records, resolved = made

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

            with self._step(ui, "Installing"):
                self._installer.install(path, self._python_candidates(resolved))

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
        index=None,
        mode: str = "source",
    ) -> _Component | None:
        """Resolve a component through the source index (ADR-20).

        ``index.resolve(name)`` returns the first exact hit in source
        order. The desired mode decides how the resource is obtained:
        ``source`` resolves the catalog ``location`` (a checkout), while
        ``artifact`` resolves the catalog ``release`` (a published
        artifact) and fails when no release is declared. There is no
        search, no name interpretation, and no fallback: an unknown
        identity resolves to nothing. ``index`` overrides the Context
        index.
        """
        hit = (index if index is not None else self._index()).resolve(target)
        if hit is None:
            return None
        catalog, ref = hit
        return self._component_from_ref(target, catalog, ref, mode=mode)

    def _component_from_ref(
        self, name: str, catalog, ref, *, mode: str = "source"
    ) -> _Component | None:
        """Resolve a catalog entry in the requested mode.

        The caller decides source vs artifact — never the shape of a
        temporary resource. ``source`` uses ``location`` (a checkout),
        ``artifact`` uses ``release`` (a published artifact). The
        component's native identity (pyproject) is read only when present,
        to assert it against the catalog and carry its mount — it never
        decides the mode.
        """
        if mode == "artifact":
            if ref.release is None:
                raise CatalogError(
                    f"component '{name}' has no release — use a --path "
                    f"catalog instead"
                )
            resource = self._materialize_release(catalog, name, ref.release)
            if resource is None:
                return None
            artifact = self._parse_artifact(resource)
            if artifact is not None:
                return _Component(name=name, mode="artifact", artifact=artifact)
            structure = resource / "structure"
            structure_dir = structure if structure.is_dir() else None
            return _Component(
                name=name,
                mode="artifact",
                source=resource,
                structure=structure_dir,
            )

        resource = self._materialize_location(catalog, ref.location)
        if resource is None:
            return None
        structure = resource / "structure"
        structure_dir = structure if structure.is_dir() else None
        pack = self._read_pack(resource)
        if pack is not None:
            if pack.name != name:
                raise CatalogIdentityError(
                    f"catalog declares '{name}' but the component is "
                    f"'{pack.name}' at {resource}"
                )
            return _Component(
                name=pack.name,
                mode="source",
                pack=Pack(name=pack.name, mount=pack.mount),
                source=resource,
                structure=structure_dir,
            )
        return _Component(
            name=name, mode="source", source=resource, structure=structure_dir
        )

    def _materialize_release(self, catalog, name: str, release: str) -> Path | None:
        """Resolve a catalog's release declaration to a local artifact."""
        if catalog.base is None:
            return fetch_github_release(catalog.spec, name, release)
        path = catalog.base / release
        return path if path.exists() else None

    def _materialize_location(self, catalog, location: str) -> Path | None:
        """Resolve a source-relative catalog location to a local resource."""
        if catalog.base is not None:
            path = catalog.base / location
            return path if path.exists() else None
        # A remote catalog (base is None) is GitHub transport today.
        return fetch_github_artifact(catalog.spec, location)

    @staticmethod
    def _parse_artifact(resource: Path):
        """Build an Artifact from a resolved ``artifact.yml`` directory."""
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
        """Read a component's native identity and mount, if any.

        Identity comes from the component's own build manifest
        (``pyproject.toml``), mount from ``mount.toml``. No pack manifest
        exists anymore — a component is its native project plus optional
        mount semantics.
        """
        manifest = path / "pyproject.toml"
        if not manifest.exists():
            return None

        with open(manifest, "rb") as f:
            data = tomllib.load(f)
        project = data.get("project", {})
        return Pack(
            name=project.get("name", path.name),
            mount=read_mount(path),
        )

    def _make_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
        force: bool,
        paths_index=None,
    ) -> tuple[list, list, list, list] | None:
        """Stage the component into the installation's component store.

        Returns (all_packs, mounts, records, resolved) or None when
        nothing is new. Staging goes through ``_ensure_component`` so
        ``install`` and ``update`` share the same mechanism; on failure
        any partially staged components are cleaned up before re-raising.
        The Python install happens later, once, over the whole resolved
        set.
        """
        if component.mode == "source":
            return self._make_pack_available(
                component, target, path, existing_packs, force
            )
        return self._make_artifact_available(
            component, target, path, existing_packs, force
        )

    def _mode_changed(self, path: Path, name: str, mode: str) -> bool:
        """Whether the component is installed in a different mode."""
        inst = self.load(path)
        if inst is None:
            return False
        record = next((c for c in inst.components if c.name == name), None)
        return record is not None and record.mode != mode

    def _make_pack_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
        force: bool,
    ) -> tuple[list, list, list, list] | None:
        """Link a source component into the installation (editable).

        Composition is explicit and lives in the catalog's bundles — a
        component never pulls further components in by itself. ``mounts``
        as a hidden dependency mechanism was removed with the pack
        manifest.
        """
        packs = [PackName(target)]
        added = [p for p in packs if p not in existing_packs or force]
        if not added:
            return None
        all_packs = existing_packs + added

        records: list[Component] = []
        mounts: list[Mount] = []
        resolved: list[_Component] = []
        try:
            for name in added:
                comp = component
                resolved.append(comp)
                record = self._ensure_component(path, str(name), comp, force=force)
                records.append(record)
                staged = self._component_structure(path, str(name))
                if record.mount and staged.exists():
                    mounts.append(Mount(source=str(staged), target=record.mount))
        except Exception:
            for record in records:
                self._cleanup_component(path, record)
            raise
        return all_packs, mounts, records, resolved

    def _make_artifact_available(
        self,
        component: _Component,
        target: str,
        path: Path,
        existing_packs: list,
        force: bool,
    ) -> tuple[list, list, list, list] | None:
        if PackName(target) in existing_packs and not force:
            return None

        all_packs = existing_packs + [PackName(target)]
        record = self._ensure_component(path, target, component, force=force)
        mounts: list[Mount] = []
        staged = self._component_structure(path, target)
        if record.mount and staged.exists():
            mounts.append(Mount(source=str(staged), target=record.mount))
        return all_packs, mounts, [record], [component]

    def _ensure_component(
        self,
        path: Path,
        name: str,
        component: _Component,
        *,
        force: bool = False,
    ) -> Component:
        """Stage ``.yak/components/<name>`` to match the resolved component.

        A component with a local ``source`` becomes an editable link;
        an artifact (released, fetched) becomes a self-contained copy.
        Only the component's ``structure/`` contribution is staged — a
        pure library without ``structure/`` is installed into the venv and
        staged nothing. The staged object is replaced when it is missing,
        of the wrong mode or ``force`` is set.
        """
        staged = self._component_structure(path, name)

        if component.source is not None:
            pack = component.pack
            mount = pack.mount if pack is not None else None
            structure = component.structure
            copy = component.mode == "artifact"
            if structure is not None and structure.is_dir():
                replace = force or self._staging_mismatch(
                    staged, mode="artifact" if copy else "source"
                )
                self._stage_structure(path, name, structure, copy=copy, replace=replace)
            return Component(
                name=name,
                mode=component.mode,
                source=str(component.source),
                mount=mount,
                package=name,
            )

        artifact = component.artifact
        if artifact is None:
            return Component(name=name, mode="artifact")
        record = Component(
            name=name,
            mode="artifact",
            version=artifact.version,
            fingerprint=artifact.fingerprint,
            mount=artifact.mount,
            package=self._wheel_dist(artifact.package_file),
        )
        if not artifact.is_meta() and artifact.structure is not None:
            replace = force or self._staging_mismatch(staged, mode="artifact")
            self._stage_structure(
                path, name, artifact.structure, copy=True, replace=replace
            )
        return record

    @staticmethod
    def _staging_mismatch(staged: Path, *, mode: str) -> bool:
        """Whether the staged structure does not match the desired mode."""
        if mode == "source":
            return not (staged.is_symlink() and staged.exists())
        return not (staged.is_dir() and not staged.is_symlink())

    @staticmethod
    def _record_mode(component: _Component) -> str:
        return component.mode

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
        """Reconcile the installation (IST) against its desired state.

        The desired set is the installation's own declared state (the
        ``.yak/environment.yml`` record); it converges with the source
        index. Components no longer desired are removed; artifact
        components whose fingerprint changed are re-staged. The
        workspace is then re-materialized from the staged component
        store only.
        """
        with self._step(ui, "Resolving"):
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
        resolved_all: list[_Component] = []

        with self._step(ui, "Reconciling"):
            for name in desired:
                existing_record = merged.get(name)
                mode = (
                    existing_record.mode if existing_record is not None else "artifact"
                )
                component = self._resolve_component(name, mode=mode)
                if component is None:
                    continue
                resolved_all.append(component)
                record = merged.get(name)
                fingerprint_drift = (
                    record is not None
                    and component.mode == "artifact"
                    and component.artifact is not None
                    and component.artifact.fingerprint
                    and component.artifact.fingerprint != record.fingerprint
                )
                mode_drift = (
                    record is not None and self._record_mode(component) != record.mode
                )
                if record is None or fingerprint_drift or mode_drift:
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
            self._installer.install(path, self._python_candidates(resolved_all))

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

        # Runtime
        pid = self.runtime.status(root)
        if pid is not None:
            issues.append(f"✓ Runtime       running (pid {pid})")
        elif (root / ".yak" / "runtime.pid").exists():
            issues.append("✘ Runtime       pid file stale — run 'yak runtime restart'")
        else:
            issues.append("— Runtime       not running")

        return issues

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
