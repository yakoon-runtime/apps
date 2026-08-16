"""The deployment.yml data contract — owned by the yak tool.

The yak tool writes the installation's store bindings at install time
(ADR-19); the runtime engine reads the same format when it starts. The
model lives in the tool, so the tool has no dependency on the platform
it creates — the platform comes into existence only through `yak
install`, it can never be a prerequisite of the tool itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RUNTIME_STORE = "runtime"
"""The reserved store name of the runtime's own infrastructure."""


@dataclass(frozen=True, slots=True)
class StoreBinding:
    """The binding of one logical store to a store factory + config."""

    store: str
    factory: str
    config: Any | None = None


@dataclass(frozen=True, slots=True)
class Installation:
    """The store bindings of one installation."""

    stores: dict[str, StoreBinding] = field(default_factory=dict)

    def binding_for(self, store: str) -> StoreBinding | None:
        return self.stores.get(store)


def load_installation(path: Path) -> Installation | None:
    """Load an installation from a deployment file, or None when absent."""
    if not path.is_file():
        return None
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    stores: dict[str, StoreBinding] = {}
    for store, raw in (data.get("stores") or {}).items():
        if not isinstance(raw, dict):
            continue
        factory = raw.get("factory")
        if not isinstance(factory, str):
            continue
        stores[store] = StoreBinding(
            store=store,
            factory=factory,
            config=raw.get("config"),
        )
    return Installation(stores=stores)


def to_dict(installation: Installation) -> dict:
    """Serialize an installation back to a deployment dict.

    Insertion order is preserved: the assembler controls the order in the
    file (the `runtime` store first, then the pack stores).
    """
    return {
        "stores": {
            store: {
                k: v
                for k, v in {
                    "factory": binding.factory,
                    "config": binding.config,
                }.items()
                if v is not None
            }
            for store, binding in installation.stores.items()
        },
    }
