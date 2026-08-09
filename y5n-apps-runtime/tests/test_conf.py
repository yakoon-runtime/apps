"""Runtime config (Phase 3, ADR-18): the deployment declares its stores.

``yakoon-runtime.yml`` gains a ``stores:`` section — a mapping of logical
store names to backend configuration. The config layer parses it into
``RuntimeConfig.stores``; ``build_runtime`` turns it into physical stores
and feeds the resolver's registry.
"""

from __future__ import annotations

from y5n.apps.runtime.conf import _from_dict


def test_stores_are_parsed_from_config():
    cfg = _from_dict(
        {
            "stores": {
                "crm": {"backend": "postgres", "dsn": "postgresql://crm"},
                "security": {"backend": "memory"},
            }
        }
    )

    assert set(cfg.stores) == {"crm", "security"}
    assert cfg.stores["crm"].backend == "postgres"
    assert cfg.stores["crm"].dsn == "postgresql://crm"
    assert cfg.stores["security"].backend == "memory"


def test_missing_stores_section_defaults_to_empty():
    cfg = _from_dict({})
    assert cfg.stores == {}


def test_invalid_store_entries_are_skipped():
    cfg = _from_dict(
        {
            "stores": {
                "crm": {"backend": "postgres"},
                "broken": "not-a-map",
            }
        }
    )

    assert set(cfg.stores) == {"crm"}
