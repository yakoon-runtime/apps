"""Assembler (ADR-19): `yak install` collects declared stores and
materializes the deployment mapping.

The scanner walks the materialized structure (packs are symlinked into
`structure/`) and reads the `stores:` declarations; the installation
writes `.yak/installation/deployment.yml` — the machine-specific mapping
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

    from y5n.apps.yak.installation.assemble import collect_declared_stores
    from y5n.runtime.engine.installation import (
        Deployment,
        Installation,
        StoreMapping,
        to_dict,
    )

    stores = collect_declared_stores(tmp_path)
    installation = Installation(
        stores={name: StoreMapping(store=name, deployment=name) for name in stores},
        deployments={name: Deployment(name=name, backend="memory") for name in stores},
    )

    deployment_file = tmp_path / "installation" / "deployment.yml"
    deployment_file.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    deployment_file.write_text(yaml.safe_dump(to_dict(installation), sort_keys=False))

    loaded = load_installation(deployment_file)
    assert loaded is not None
    assert set(loaded.stores) == {"crm", "telemetry"}
    assert loaded.deployment_for("crm") is not None
    assert loaded.deployment_for("crm").backend == "memory"
