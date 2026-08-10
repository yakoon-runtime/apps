"""Assembler (ADR-19): collect the declared stores of the installed packs.

`yak install` reads the declared `stores:` of every installed pack and
materializes the deployment mapping. The scanner walks the materialized
structure — the same way the runtime's `StoreCollector` walks the tree,
but at install time, before the runtime exists.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


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
