from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from y5n.apps.yak.cap.models import Cap, CapName, Mount, read_component, read_mount
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
from y5n.apps.yak.repository.artifact import ArtifactStore
from y5n.apps.yak.repository.interface import Repository
from y5n.apps.yak.resolver.artifact import (
    Artifact,
    DirectorySource,
    _parse_manifest,
)
from y5n.apps.yak.resolver.catalog import (
    CatalogError,
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
    pack: Cap | None = None
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

    def _resolve_preferred(
        self, target: str, *, paths_index=None, mode: str = "artifact"
    ):
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
        """Make an identity part of the environment (ADR-21).

        ``install`` changes the declaration (``environment.yml``) so that
        ``identity`` is desired, then converges the environment to it.
        ``paths`` are repeatable ``--path`` catalogs that belong to this
        install decision and are stored per identity. On an existing
        environment the identity's entry is replaced — ``install system``
        after ``install system --path ./caps-system`` drops the override
        and converges back to artifacts.
        """
        root = path.resolve()
        env_file = root / ".yak" / "environment.yml"
        env = load_env(root)
        if env is None and env_file.exists():
            raise RuntimeError(
                "environment.yml uses the old schema (a resolved component "
                "list). Reinitialize: rm -rf .yak .venv && yak init && "
                "yak install ..."
            )
        paths_list = [str(p) for p in (paths or [])]
        if env is not None and env.install.get(identity) == paths_list:
            # Already declared exactly as requested — nothing to change.
            return None
        declaration = dict(env.install) if env else {}
        declaration[identity] = paths_list
        return self._reconcile(
            root,
            install=declaration,
            ui=ui,
            asker=asker,
            workspace_path=workspace_path,
        )

    def _reconcile(
        self,
        path: Path,
        *,
        install: dict[str, list[str]],
        ui=None,
        asker: StoreAsker | None = None,
        workspace_path: str = "structure",
    ) -> Installation:
        """Converge the environment to a declaration (SOLL → IST).

        ``install`` maps identities to their ``--path`` overrides; each
        identity's bundle is resolved against the current catalogs and
        every component resolves per component: a ``--path`` hit is a
        source, everything else a release (artifact). Components no
        longer desired are removed, drifted artifacts re-staged, and the
        whole set is installed in one pip transaction. ``state.toml`` is
        the truth about an established environment: it is written only
        after the transaction succeeded, so a failed run leaves the
        previous state intact.
        """
        root = path.resolve()
        env = load_env(root)
        inst = self.load(root)
        if inst is not None and inst.status == InstallationStatus.RUNNING:
            raise RuntimeError(f"Cannot update running installation: {inst.name}")

        env_name = env.name if env else (root.name or "yakoon")
        structure_dir = (
            env.workspace_dir(root) if env else root / ".yak" / workspace_path
        )

        # The environment-wide preferred source index: the union of all
        # active --path overrides. Ownership is per identity (an override
        # dies with its identity); resolution uses the union — one
        # environment, not isolated install islands.
        all_paths = sorted({p for paths in install.values() for p in paths})
        combined = self._combined_index(all_paths)
        paths_index = self._paths_index(all_paths)

        desired: list[str] = []
        with self._step(ui, "Resolving"):
            for identity in install:
                for member in self._identities(identity, index=combined):
                    if member not in desired:
                        desired.append(member)

        merged = {c.name: c for c in (inst.components if inst else [])}
        original_names = set(merged)
        resolved_all: list[_Component] = []
        backups: dict[str, Path] = {}
        try:
            with self._step(ui, "Reconciling"):
                # Resolution is network-bound (release digests, downloads)
                # and independent per component — resolve concurrently so
                # the wall time is one round-trip, not one per component.
                resolved: dict[str, _Component] = {}
                with ThreadPoolExecutor(max_workers=8) as pool:
                    futures = {
                        pool.submit(
                            self._resolve_preferred, name, paths_index=paths_index
                        ): name
                        for name in desired
                    }
                    for future in as_completed(futures):
                        name = futures[future]
                        component = future.result()
                        if component is None:
                            raise CatalogError(
                                f"component '{name}' cannot be resolved "
                                f"(declared by an installed identity)"
                            )
                        resolved[name] = component

                changed: set[str] = set()
                for name in desired:
                    component = resolved[name]
                    existing_record = merged.get(name)
                    drift = existing_record is not None and (
                        component.mode != existing_record.mode
                        or (
                            component.mode == "artifact"
                            and component.artifact is not None
                            and component.artifact.fingerprint
                            and component.artifact.fingerprint
                            != existing_record.fingerprint
                        )
                    )
                    if existing_record is None or drift:
                        # Preserve the previously staged structure (AAA)
                        # so a failed transaction can restore it — the
                        # workspace must never show BBB while state and
                        # venv are still AAA.
                        if existing_record is not None:
                            backup = self._backup_structure(root, name)
                            if backup is not None:
                                backups[name] = backup
                        merged[name] = self._ensure_component(
                            root, name, component, force=True
                        )
                        changed.add(name)
                    else:
                        merged[name] = self._ensure_component(root, name, component)

                # Only components that are new or changed are handed to pip:
                # a no-op update reinstalls nothing.
                resolved_all = [resolved[name] for name in desired if name in changed]

            obsolete = [n for n in merged if n not in desired]
            self._remove_orphans(root, set(desired))

            new_records = [merged.get(n, Component(name=n)) for n in desired]
            component_mounts = self._component_mounts(root, new_records)
            manual = [
                m for m in (env.mounts if env else []) if m not in component_mounts
            ]
            all_mounts = component_mounts + manual

            with self._step(ui, "Workspace"):
                self._materializer.materialize(
                    structure_dir,
                    mounts=all_mounts,
                    components_dir=self._components_dir(root),
                )

            with self._step(ui, "Deployment"):
                existing_dep = load_installation(root / ".yak" / "deployment.yml")
                self._assemble(
                    structure_dir, root / ".yak", existing=existing_dep, asker=asker
                )

            with self._step(ui, "Installing"):
                self._installer.install(root, self._python_candidates(resolved_all))
        except Exception:
            # The run failed before the state was committed. Restore the
            # preserved structures of drifted components (the workspace
            # must look like AAA again — state still says AAA), then
            # clean up freshly staged components so no residue claims
            # them. Previously installed components that did not drift
            # stay untouched. State is never rewritten on failure.
            for name, backup in backups.items():
                self._restore_backup(root, name, backup)
            for name in desired:
                if name not in original_names:
                    self._cleanup_component(
                        root, merged.get(name, Component(name=name))
                    )
            raise

        # Preserved structures are no longer needed once the transaction
        # succeeded.
        for backup in backups.values():
            if backup.exists() or backup.is_symlink():
                if backup.is_symlink() or backup.is_file():
                    backup.unlink()
                else:
                    shutil.rmtree(backup)

        # Removals only after the install transaction succeeded: a failed
        # run must never uninstall ahead of a broken state.
        for name in obsolete:
            self._remove_component(root, name)

        with self._step(ui, "Environment"):
            env = touch(
                root,
                name=env_name,
                install=install,
                mounts=all_mounts,
                workspace_path=env.workspace_path if env else workspace_path,
            )

        now = datetime.now(UTC)
        inst = Installation(
            name=env_name,
            root=root,
            packs=[CapName(c.name) for c in new_records],
            components=new_records,
            status=InstallationStatus.CREATED,
            created=now if inst is None else inst.created,
            updated=now,
        )
        # State is the truth about an established environment: written
        # only after the pip transaction succeeded. A failed install or
        # update leaves the previous state (or none) intact.
        self._write_state(inst)
        return inst

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

    def _identities(self, identity: str, *, index: Index | None = None) -> list[str]:
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
        ``artifact`` finds the offered release. The catalog key is a
        discovery binding only (ADR-23 Step 4): the component's own
        contract is validated at the actual access — the source's
        ``.yak/component.yml`` or the artifact's ``artifact.yml`` must
        declare exactly the expected name, and a mismatch fails loudly.
        """
        if mode == "artifact":
            resource = self._materialize_release(catalog, name, ref.location)
            if resource is None:
                return None
            artifact = self._parse_artifact(resource)
            if artifact is not None:
                self._validate_identity(
                    expected=name,
                    actual=artifact.name,
                    what=f"artifact.yml of '{name}' from '{catalog.spec}'",
                )
                return _Component(name=name, mode="artifact", artifact=artifact)
            structure_dir = self._mounted_dir(resource)
            return _Component(
                name=name,
                mode="artifact",
                source=resource,
                structure=structure_dir,
            )

        resource = self._materialize_location(catalog, ref.location)
        if resource is None:
            return None
        pack = self._read_component(resource)
        actual = pack.name if pack is not None else None
        self._validate_identity(
            expected=name,
            actual=actual,
            what=f"the component at '{ref.location}' in '{catalog.spec}'",
        )
        structure_dir = self._component_mount_dir(resource, pack)
        return _Component(
            name=name,
            mode="source",
            pack=pack,
            source=resource,
            structure=structure_dir,
        )

    @staticmethod
    def _mounted_dir(resource: Path) -> Path | None:
        """The mounted content inside a fetched resource.

        Artifacts package the mounted content into the canonical ``mount``
        subdirectory; ``structure`` remains a read fallback for artifacts
        built before that name existed.
        """
        for candidate in ("mount", "structure"):
            path = resource / candidate
            if path.is_dir():
                return path
        return None

    @staticmethod
    def _component_mount_dir(resource: Path, pack: Cap | None) -> Path | None:
        """The component-relative mount source, resolved against the source.

        The component's delivery is declared in ``.yak/mount.yml``
        (source → path), never by a hard-coded directory name. A declared
        source that does not exist is a contract violation and fails
        loudly — a mount without content is a broken component.
        """
        if pack is None or pack.mount is None:
            return None
        mounted = resource / pack.mount.source
        if not mounted.is_dir():
            raise CatalogError(
                f"component '{pack.name}' declares mount source "
                f"'{pack.mount.source}' in .yak/mount.yml but "
                f"'{mounted}' is not a directory"
            )
        return mounted

    def _validate_identity(self, expected: str, actual: str | None, what: str) -> None:
        """A catalog key must match the component's own declared identity.

        The catalog key is a discovery binding, never a normative identity
        (ADR-23 Step 4). Whenever the component is actually accessed the
        expected name is checked against its own contract and a mismatch
        fails loudly and unambiguously.
        """
        if actual is None:
            raise CatalogError(
                f"{what} has no .yak/component.yml / artifact.yml "
                "(so no declared identity)"
            )
        if actual != expected:
            raise CatalogError(
                f"identity mismatch for '{expected}': the catalog key does "
                f"not match the component's own declaration ({what} "
                f"declares '{actual}')"
            )

    def _materialize_release(self, catalog, name: str, location: str) -> Path | None:
        """Resolve a component's released artifact from its distribution.

        A component's distribution defaults to the source of the catalog
        that discovered it (ADR-23 Step 3): a local source carries its
        released artifacts in ``artifacts/`` under the catalog root; a
        remote source resolves the component's own ``.yak/release.yml`` at
        its catalog ``location`` and publishes releases to its repository.
        The catalog names the source; it never names a version.
        """
        if catalog.base is not None:
            artifact = DirectorySource(catalog.base / "artifacts").resolve(name)
            if artifact is None or artifact.path is None:
                raise CatalogError(
                    f"component '{name}' has no release — use a --path "
                    f"catalog instead"
                )
            return artifact.path
        if not catalog.spec.startswith("github:"):
            raise CatalogError(
                f"component '{name}' has no remote distribution — source "
                f"'{catalog.spec}' is local"
            )
        return fetch_github_release(catalog.spec, name, location)

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
        from y5n.apps.yak.resolver.artifact import _mount_target

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
            mount=_mount_target(meta.get("mount")),
        )

    # ── Context source mapping (removed in ADR-20; sources replace it) ──

    @staticmethod
    def _read_component(path: Path) -> Cap | None:
        """Read a component's identity and mount, if any.

        Identity and version come from the component's Yakoon contract
        ``.yak/component.yml`` (ADR-23); mount from ``.yak/mount.yml``.
        No pack manifest exists anymore — a component is its native
        project plus optional mount semantics.
        """
        return read_component(path)

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
            mount = (
                pack.mount.target
                if pack is not None and pack.mount is not None
                else None
            )
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
        """Converge the installation to its declaration (environment.yml).

        Unlike ``install`` the declaration is not changed: the stored
        identities and their ``--path`` overrides are re-resolved against
        the current catalogs, so bundle growth, shrinkage and new builds
        of the same version become visible. State (IST) is written only
        after the install transaction succeeded.
        """
        root = path.resolve()
        env = load_env(root)
        if env is None:
            raise ValueError(f"Installation not found at {path}")
        return self._reconcile(root, install=env.install, ui=ui, asker=asker)

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
                f"✓ Environment   {len(env.mounts)} mount(s), {len(env.install)} identity(s)"
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

        # Orphans: staged components that are not part of the installation.
        desired = {c.name for c in inst.components}
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

    def _backup_structure(self, path: Path, name: str) -> Path | None:
        """Move a staged structure aside so a failed run can restore it.

        Returns the backup path, or None when nothing was staged. The
        move is an atomic rename and keeps the previous mode (symlink for
        source, directory for artifact).
        """
        staged = self._component_structure(path, name)
        if not (staged.exists() or staged.is_symlink()):
            return None
        backup = staged.with_name(staged.name + ".bak")
        if backup.exists() or backup.is_symlink():
            if backup.is_symlink() or backup.is_file():
                backup.unlink()
            else:
                shutil.rmtree(backup)
        os.replace(staged, backup)
        return backup

    def _restore_backup(self, path: Path, name: str, backup: Path) -> None:
        """Put a preserved structure back in place after a failed run."""
        staged = self._component_structure(path, name)
        if staged.exists() or staged.is_symlink():
            if staged.is_symlink() or staged.is_file():
                staged.unlink()
            else:
                shutil.rmtree(staged)
        if backup.exists() or backup.is_symlink():
            os.replace(backup, staged)

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
            packs=[CapName(p) for p in inst_data.get("packs", [])],
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
