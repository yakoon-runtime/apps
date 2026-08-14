"""Assembler (ADR-19): `yak install` collects declared stores and
materializes the deployment mapping.

The scanner walks the materialized structure (packs are symlinked into
`structure/`) and reads the `stores:` declarations; the installation
writes `.yak/deployment.yml` — the machine-specific mapping
owned by `yak`.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.installation.assemble import collect_declared_stores
from y5n.runtime.engine.installation import load_installation


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_collect_declared_stores_across_packs(tmp_path: Path):
    _write(
        tmp_path / "crm" / ".yak" / "yak.yml",
        "stores:\n  - crm\n",
    )
    _write(
        tmp_path / "luma" / ".yak" / "yak.yml",
        "stores:\n  - luma\n",
    )
    _write(
        tmp_path / "ident" / ".yak" / "yak.yml",
        "stores:\n  - ident\n",
    )

    assert collect_declared_stores(tmp_path) == ["crm", "ident", "luma"]


def test_collect_deduplicates_and_ignores_non_strings(tmp_path: Path):
    _write(
        tmp_path / "a" / ".yak" / "yak.yml",
        "stores:\n  - crm\n  - crm\n  - name: structured\n",
    )
    _write(
        tmp_path / "b" / ".yak" / "yak.yml",
        "host: /boot/python/runtime\n",
    )

    assert collect_declared_stores(tmp_path) == ["crm"]


def test_installation_roundtrip(tmp_path: Path):
    _write(
        tmp_path / "crm" / ".yak" / "yak.yml",
        "stores:\n  - crm\n",
    )
    _write(
        tmp_path / "telemetry" / ".yak" / "yak.yml",
        "stores:\n  - telemetry\n",
    )

    from y5n.apps.yak.installation.assemble import (
        EVENT_STORE_FACTORY,
        MEMORY_CONFIG,
        build_memory_installation,
        collect_declared_stores,
    )
    from y5n.runtime.engine.installation import RUNTIME_STORE, to_dict

    stores = collect_declared_stores(tmp_path)
    installation = build_memory_installation(stores)

    deployment_file = tmp_path / "installation" / "deployment.yml"
    deployment_file.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    deployment_file.write_text(yaml.safe_dump(to_dict(installation), sort_keys=False))

    loaded = load_installation(deployment_file)
    assert loaded is not None
    assert set(loaded.stores) == {RUNTIME_STORE, "crm", "telemetry"}
    assert loaded.binding_for("crm") is not None
    assert loaded.binding_for("crm").factory == EVENT_STORE_FACTORY
    assert loaded.binding_for("crm").config == MEMORY_CONFIG
    assert loaded.binding_for(RUNTIME_STORE) is not None


def test_memory_installation_always_binds_the_runtime_store(tmp_path: Path):
    from y5n.apps.yak.installation.assemble import build_memory_installation
    from y5n.runtime.engine.installation import RUNTIME_STORE

    installation = build_memory_installation([])
    assert installation.binding_for(RUNTIME_STORE) is not None
    assert set(installation.stores) == {RUNTIME_STORE}


class _StubAsker:
    def __init__(self, backends: dict[str, str]) -> None:
        self._backends = backends
        self._dsns: dict[str, str] = {}

    def backend(self, store: str) -> str:
        return self._backends.get(store, "memory")

    def dsn(self, store: str, default: str) -> str:
        self._dsns[store] = default
        return default


def test_assemble_with_asker_binds_operator_backends():
    from y5n.apps.yak.installation.assemble import (
        EVENT_STORE_FACTORY,
        assemble_installation,
    )
    from y5n.runtime.engine.installation import RUNTIME_STORE

    asker = _StubAsker({"crm": "postgres", "ident": "memory"})
    installation = assemble_installation(["crm", "ident"], asker=asker)

    crm = installation.binding_for("crm")
    assert crm is not None
    assert crm.factory == EVENT_STORE_FACTORY
    assert crm.config == {"backend": "postgres", "dsn": "env://CRM_DATABASE"}

    ident = installation.binding_for("ident")
    assert ident is not None
    assert ident.config == {"backend": "memory"}

    # The runtime store is never asked — always bound to memory.
    runtime = installation.binding_for(RUNTIME_STORE)
    assert runtime is not None
    assert runtime.config == {"backend": "memory"}
    assert asker._backends.get(RUNTIME_STORE, "memory") == "memory"


def test_assemble_reuses_existing_bindings_and_asks_only_new_stores():
    from y5n.apps.yak.installation.assemble import assemble_installation
    from y5n.runtime.engine.installation import Installation, StoreBinding

    existing = Installation(
        stores={
            "crm": StoreBinding(
                store="crm",
                factory="y5n.runtime.store.event.wire:EventStoreFactory",
                config={"backend": "postgres", "dsn": "postgresql://.../yakoon_crm"},
            )
        }
    )
    asker = _StubAsker({"telemetry": "memory"})
    installation = assemble_installation(
        ["crm", "telemetry"], existing=existing, asker=asker
    )

    # Existing binding survived untouched — the asker never saw it.
    crm = installation.binding_for("crm")
    assert crm is not None
    assert crm.config == {"backend": "postgres", "dsn": "postgresql://.../yakoon_crm"}
    assert "crm" not in asker._backends

    # Newly declared store was asked.
    assert installation.binding_for("telemetry") is not None
