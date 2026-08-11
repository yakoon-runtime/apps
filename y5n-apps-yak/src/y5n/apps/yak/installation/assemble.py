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

import yaml
from y5n.runtime.engine.installation import (
    RUNTIME_STORE,
    Installation,
    StoreBinding,
)

EVENT_STORE_FACTORY = "y5n.runtime.store.event.wire:EventStoreFactory"
"""The factory path for the event store — the default memory backend."""

MEMORY_CONFIG = {"backend": "memory"}


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
    stores: dict[str, StoreBinding] = {
        RUNTIME_STORE: StoreBinding(
            store=RUNTIME_STORE,
            factory=EVENT_STORE_FACTORY,
            config=dict(MEMORY_CONFIG),
        ),
    }
    for name in store_names:
        stores[name] = StoreBinding(
            store=name,
            factory=EVENT_STORE_FACTORY,
            config=dict(MEMORY_CONFIG),
        )
    return Installation(stores=stores)
