"""Assembler (ADR-19): collect the declared stores of the installed packs.

`yak install` reads the declared `stores:` of every installed pack and
materializes the deployment. The scanner walks the materialized structure
— the same way the runtime's `StoreCollector` walks the tree, but at
install time, before the runtime exists.

The installation also always carries the runtime's own infrastructure
store `runtime`: the runtime requires it (session, activity) and it is a
plain installation requirement like any other — its peculiarity lies
only in *who requires it* (ADR-19).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import yaml
from y5n.runtime.engine.installation import (
    RUNTIME_STORE,
    Installation,
    StoreBinding,
)

EVENT_STORE_FACTORY = "y5n.runtime.store.event.wire:EventStoreFactory"
"""The factory path for the event store — the default memory backend."""

MEMORY_CONFIG = {"backend": "memory"}
"""The config of the default in-memory event store."""

POSTGRES_BACKEND = "postgres"


class StoreAsker(Protocol):
    """The questions the assembler asks the operator per declared store."""

    def backend(self, store: str) -> str: ...

    def dsn(self, store: str, default: str) -> str: ...


def collect_declared_stores(structure_dir: Path) -> list[str]:
    """Collect the declared store names across the installed packs.

    Walks the materialized structure for `.yak/yak.yml` files and reads
    their `stores:` list. Symlinks are followed (packs are mounted into
    `structure/`), and store names are de-duplicated and sorted.
    """
    names: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(structure_dir, followlinks=True):
        if dirpath.endswith(".yak") and "yak.yml" in filenames:
            yml = Path(dirpath) / "yak.yml"
            try:
                data = yaml.safe_load(yml.read_text()) or {}
            except (OSError, yaml.YAMLError):
                continue
            for name in data.get("stores") or []:
                if isinstance(name, str):
                    names.add(name)
        # Do not descend into arbitrary symlinked trees beyond .yak dirs.
        dirnames[:] = [
            d
            for d in dirnames
            if not (Path(dirpath) / d).is_symlink()
            or (Path(dirpath) / d / ".yak").exists()
        ]
    return sorted(names)


def build_memory_installation(store_names: list[str]) -> Installation:
    """Materialize a memory-backed installation for the declared stores.

    The installation binds the runtime's own `runtime` store (always
    required) plus every store the installed packs declare — all to the
    in-memory event store. This is the developer default; a real
    deployment points the factories at physical backends.
    """
    return assemble_installation(store_names, existing=None, asker=None)


def assemble_installation(
    store_names: list[str],
    existing: Installation | None = None,
    asker: StoreAsker | None = None,
) -> Installation:
    """Assemble the installation for the declared stores.

    The `runtime` store — the runtime's own session/activity
    infrastructure — is always bound, by default to the in-memory event
    store. Every other declared store defaults to memory; with an asker
    the operator picks the backend and, for `postgres`, the DSN.

    Existing bindings are reused untouched: on update only newly declared
    stores are asked, while the operator's previous choices survive
    (ADR-19, open question #4).
    """
    stores: dict[str, StoreBinding] = {}

    runtime = existing.binding_for(RUNTIME_STORE) if existing is not None else None
    stores[RUNTIME_STORE] = runtime or StoreBinding(
        store=RUNTIME_STORE,
        factory=EVENT_STORE_FACTORY,
        config=dict(MEMORY_CONFIG),
    )

    for name in store_names:
        if name == RUNTIME_STORE:
            continue
        binding = existing.binding_for(name) if existing is not None else None
        if binding is not None:
            stores[name] = binding
            continue
        stores[name] = _ask_binding(name, asker)

    return Installation(stores=stores)


def _ask_binding(name: str, asker: StoreAsker | None) -> StoreBinding:
    """Bind one declared store — memory by default, operator-guided if asked."""
    if asker is None:
        return StoreBinding(
            store=name,
            factory=EVENT_STORE_FACTORY,
            config=dict(MEMORY_CONFIG),
        )
    backend = asker.backend(name)
    config: dict[str, str] = {"backend": backend}
    if backend == POSTGRES_BACKEND:
        default = f"env://{name.upper()}_DATABASE"
        dsn = asker.dsn(name, default) or default
        config["dsn"] = dsn
    return StoreBinding(store=name, factory=EVENT_STORE_FACTORY, config=config)
