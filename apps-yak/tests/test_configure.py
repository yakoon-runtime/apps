"""yak configure (ADR-19 operator path): rebind existing stores.

The installer materializes missing bindings with memory defaults; the
configure command changes the operator's deployment decision for a store
that is already bound — and nothing else. Configuring never creates a
store and never changes a factory.
"""

from __future__ import annotations

import types

import yaml
import pytest


def _write_deployment(path, stores) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"stores": stores}, sort_keys=False))


def _memory_binding(name: str, config=None):
    from y5n.apps.yak.installation.deployment import StoreBinding

    return StoreBinding(
        store=name,
        factory="y5n.runtime.store.event.wire:EventStoreFactory",
        config=config or {"backend": "memory"},
    )


@pytest.fixture
def installation():
    from y5n.apps.yak.installation.deployment import Installation

    runtime = _memory_binding("runtime")
    contacts = _memory_binding("contacts")
    ident = _memory_binding("ident")
    return Installation(
        stores={"runtime": runtime, "contacts": contacts, "ident": ident}
    )


def test_memory_to_postgres_binds_dsn_and_keeps_factory(installation):
    from y5n.apps.yak.installation.configure import configure_store

    result = configure_store(
        installation, "contacts", "postgres", "env://CONTACTS_DATABASE"
    )

    contacts = result.binding_for("contacts")
    assert contacts is not None
    assert contacts.factory == "y5n.runtime.store.event.wire:EventStoreFactory"
    assert contacts.config == {
        "backend": "postgres",
        "dsn": "env://CONTACTS_DATABASE",
    }
    assert result.binding_for("runtime") is installation.binding_for("runtime")


def test_postgres_to_memory_removes_the_dsn(installation):
    from y5n.apps.yak.installation.configure import configure_store

    installation = configure_store(
        installation, "contacts", "postgres", "postgresql://db"
    )
    result = configure_store(installation, "contacts", "memory")

    contacts = result.binding_for("contacts")
    assert contacts is not None
    assert contacts.config == {"backend": "memory"}
    assert "dsn" not in contacts.config


def test_configure_keeps_all_other_bindings(installation):
    from y5n.apps.yak.installation.configure import configure_store

    result = configure_store(installation, "ident", "postgres", "env://IDENT_DATABASE")

    assert result.binding_for("contacts") is installation.binding_for("contacts")
    assert result.binding_for("runtime") is installation.binding_for("runtime")
    contacts_cfg = result.binding_for("ident")
    assert contacts_cfg is not None
    assert contacts_cfg.factory == installation.binding_for("ident").factory


def test_configure_unknown_store_raises(installation):
    from y5n.apps.yak.installation.configure import configure_store

    with pytest.raises(KeyError):
        configure_store(installation, "worlds", "postgres", "env://WORLDS_DATABASE")


def test_configure_rejects_unsupported_backend(installation):
    from y5n.apps.yak.installation.configure import configure_store

    with pytest.raises(ValueError):
        configure_store(installation, "contacts", "redis")


def test_configure_postgres_requires_a_dsn(installation):
    from y5n.apps.yak.installation.configure import configure_store

    with pytest.raises(ValueError):
        configure_store(installation, "contacts", "postgres", "")


def test_default_dsn_keeps_an_existing_one(installation):
    from y5n.apps.yak.installation.configure import default_dsn

    from y5n.apps.yak.installation.configure import configure_store

    postgres = configure_store(
        installation, "contacts", "postgres", "postgresql://prod/db"
    )
    assert (
        default_dsn(postgres.binding_for("contacts"), "contacts")
        == "postgresql://prod/db"
    )
    assert (
        default_dsn(installation.binding_for("ident"), "ident")
        == "env://IDENT_DATABASE"
    )


# ---------------------------------------------------------------
# Command level
# ---------------------------------------------------------------


def _args(**kw) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


def _make_env(tmp_path) -> None:
    _write_deployment(
        tmp_path / ".yak" / "deployment.yml",
        {
            "runtime": {
                "factory": "y5n.runtime.store.event.wire:EventStoreFactory",
                "config": {"backend": "memory"},
            },
            "contacts": {
                "factory": "y5n.runtime.store.event.wire:EventStoreFactory",
                "config": {"backend": "memory"},
            },
            "ident": {
                "factory": "y5n.runtime.store.event.wire:EventStoreFactory",
                "config": {"backend": "memory"},
            },
        },
    )


def test_command_configures_a_named_store_directly(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )
    monkeypatch.setattr(
        configure_cmd, "_ask_dsn", lambda store, default: "env://CONTACTS_DATABASE"
    )

    configure_cmd.run(
        _args(target=str(tmp_path), store="contacts", verbose=False), None
    )

    installation = load_installation(tmp_path / ".yak" / "deployment.yml")
    assert installation.binding_for("contacts").config == {
        "backend": "postgres",
        "dsn": "env://CONTACTS_DATABASE",
    }
    # All other bindings survived untouched.
    assert installation.binding_for("runtime").config == {"backend": "memory"}
    assert installation.binding_for("ident").config == {"backend": "memory"}


def test_command_walks_all_stores_when_no_store_given(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )
    monkeypatch.setattr(
        configure_cmd,
        "_ask_dsn",
        lambda store, default: f"env://{store.upper()}_DATABASE",
    )

    configure_cmd.run(_args(target=str(tmp_path), store=None, verbose=False), None)

    installation = load_installation(tmp_path / ".yak" / "deployment.yml")
    for name in ("runtime", "contacts", "ident"):
        binding = installation.binding_for(name)
        assert binding is not None
        assert binding.config == {
            "backend": "postgres",
            "dsn": f"env://{name.upper()}_DATABASE",
        }


def test_command_defaults_to_the_existing_config(tmp_path, monkeypatch):
    """Pressing Enter keeps the current binding — configure is an editor."""
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd

    _write_deployment(
        tmp_path / ".yak" / "deployment.yml",
        {
            "runtime": {
                "factory": "y5n.runtime.store.event.wire:EventStoreFactory",
                "config": {"backend": "memory"},
            },
            "contacts": {
                "factory": "y5n.runtime.store.event.wire:EventStoreFactory",
                "config": {"backend": "postgres", "dsn": "postgresql://prod/db"},
            },
        },
    )
    before = (tmp_path / ".yak" / "deployment.yml").read_text()
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )

    def fake_dsn(store: str, default: str) -> str:
        captured["default"] = default
        return default

    monkeypatch.setattr(configure_cmd, "_ask_dsn", fake_dsn)

    configure_cmd.run(
        _args(target=str(tmp_path), store="contacts", verbose=False), None
    )

    assert captured["default"] == "postgresql://prod/db"
    assert (tmp_path / ".yak" / "deployment.yml").read_text() == before


def test_command_refuses_an_uninstalled_store(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd

    _make_env(tmp_path)
    before = (tmp_path / ".yak" / "deployment.yml").read_text()

    configure_cmd.run(_args(target=str(tmp_path), store="worlds", verbose=False), None)

    assert (tmp_path / ".yak" / "deployment.yml").read_text() == before


def test_command_no_deployment_is_a_clean_fail(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd

    monkeypatch.setattr(configure_cmd, "find_runtime_root", lambda: None)

    configure_cmd.run(
        _args(target=str(tmp_path / "empty"), store=None, verbose=False), None
    )

    assert not (tmp_path / "empty" / ".yak" / "deployment.yml").exists()
