"""Configure existing store bindings (ADR-19, operator path).

`yak install` materializes missing bindings with safe defaults (memory);
`yak configure` changes the operator's deployment decision for a store
that is already bound. Configuring never creates a store — an unknown
store is an error, so declared need keeps coming exclusively from
install/assembly.

`configure_store` rebinds one store; it preserves the binding's factory
and touches nothing else. The writer is the same one install uses, so the
deployment file stays the single, human-readable surface for both.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.installation.deployment import Installation, StoreBinding

MEMORY_BACKEND = "memory"
POSTGRES_BACKEND = "postgres"


def configure_store(
    installation: Installation,
    store: str,
    backend: str,
    dsn: str | None = None,
) -> Installation:
    """Rebind an existing store to ``backend`` (and ``dsn`` for postgres).

    The factory is preserved — configuration never changes what
    materializes a store, only how. An unknown store raises ``KeyError``:
    need is declared by install, never invented here.
    """
    binding = installation.binding_for(store)
    if binding is None:
        raise KeyError(
            f"Store '{store}' is not installed — configure never creates "
            "stores. Run 'yak install' first."
        )
    if backend not in (MEMORY_BACKEND, POSTGRES_BACKEND):
        raise ValueError(f"Unsupported backend: {backend!r}")

    config: dict[str, str] = {"backend": backend}
    if backend == POSTGRES_BACKEND:
        if not dsn:
            raise ValueError(f"backend '{POSTGRES_BACKEND}' requires a dsn")
        config["dsn"] = dsn

    stores = dict(installation.stores)
    stores[store] = StoreBinding(store=store, factory=binding.factory, config=config)
    return Installation(stores=stores)


def default_dsn(binding: StoreBinding | None, store: str) -> str:
    """The dsn suggested when configuring a store as postgres.

    A store already bound to postgres keeps its operator-chosen dsn; a
    memory (or unconfigured) store falls back to the conventional
    ``env://NAME`` reference.
    """
    if binding is not None:
        config = binding.config
        if isinstance(config, dict) and config.get("backend") == POSTGRES_BACKEND:
            existing = config.get("dsn")
            if existing:
                return str(existing)
    return f"env://{store.upper()}_DATABASE"


def write_deployment(installation: Installation, path: Path) -> None:
    """Write an installation with the same writer install uses."""
    import yaml

    from y5n.apps.yak.installation.deployment import to_dict

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(to_dict(installation), f, sort_keys=False)
