"""yak configure (ADR-19 operator path): rebind existing stores.

The installer materializes missing bindings with memory defaults; the
configure command changes the operator's deployment decision for a store
that is already bound — and nothing else. Configuring never creates a
store and never changes a factory.
"""

from __future__ import annotations

import types

import pytest
import yaml


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
    from y5n.apps.yak.installation.configure import configure_store, default_dsn

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


ADMIN_MODULE = "y5n.runtime.store.event.backends.postgres.admin"


def _admin_calls(run) -> int:
    return sum(1 for c in run.calls if c[1:3] == ["-m", ADMIN_MODULE])


def _missing_stderr(database: str) -> str:
    return (
        "Traceback (most recent call last):\n"
        "...\n"
        f'DatabaseDoesNotExist: database "{database}" does not exist'
    )


class _RecordingRun:
    """A fake subprocess.run that records commands and snapshots the
    deployment file at call time."""

    def __init__(self, *, fail_at: int | None = None, deployment_file=None):
        self.calls: list[list[str]] = []
        self.snapshots: list[str] = []
        self._fail_at = fail_at
        self._deployment_file = deployment_file

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self._deployment_file is not None:
            self.snapshots.append(self._deployment_file.read_text())
        if self._fail_at is not None and len(self.calls) == self._fail_at:
            return types.SimpleNamespace(
                returncode=1, stderr="provision failed", stdout=""
            )
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")


class _ScriptedRun:
    """A fake subprocess.run returning a scripted result per call."""

    def __init__(self, responses, *, deployment_file=None):
        self.responses = list(responses)
        self.calls: list[list[str]] = []
        self.snapshots: list[str] = []
        self._deployment_file = deployment_file

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self._deployment_file is not None:
            self.snapshots.append(self._deployment_file.read_text())
        rc, stderr, stdout = self.responses.pop(0)
        return types.SimpleNamespace(returncode=rc, stderr=stderr, stdout=stdout)


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
    _venv_python(tmp_path)


def _venv_python(tmp_path) -> None:
    bin_dir = tmp_path / ".venv" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "python").touch()


def _patch_provision_run(monkeypatch, configure_cmd, recorder) -> None:
    monkeypatch.setattr(configure_cmd.subprocess, "run", recorder)


def test_command_configures_a_named_store_directly(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    recorder = _RecordingRun(deployment_file=tmp_path / ".yak" / "deployment.yml")
    _patch_provision_run(monkeypatch, configure_cmd, recorder)
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

    # `yak configure <store>` provisions exactly that one store.
    assert len(recorder.calls) == 1
    contacts_call = recorder.calls[0]
    assert contacts_call[0] == str(tmp_path / ".venv" / "bin" / "python")
    assert contacts_call[1:3] == ["-m", "y5n.runtime.engine.provision"]
    assert '"backend": "postgres"' in contacts_call[4]
    assert '"env://CONTACTS_DATABASE"' in contacts_call[4]


def test_command_walks_all_stores_when_no_store_given(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    recorder = _RecordingRun(deployment_file=tmp_path / ".yak" / "deployment.yml")
    _patch_provision_run(monkeypatch, configure_cmd, recorder)
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
    assert len(recorder.calls) == 3
    assert recorder.calls[2][3] == "y5n.runtime.store.event.wire:EventStoreFactory"
    # A reachable database needs no admin operation.
    assert _admin_calls(recorder) == 0


def test_command_writes_entire_deployment_before_provisioning(tmp_path, monkeypatch):
    """write-before-provision: at the first provision call the deployment
    file already carries the final state."""
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd

    _make_env(tmp_path)
    recorder = _RecordingRun(deployment_file=tmp_path / ".yak" / "deployment.yml")
    _patch_provision_run(monkeypatch, configure_cmd, recorder)
    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )
    monkeypatch.setattr(
        configure_cmd,
        "_ask_dsn",
        lambda store, default: f"env://{store.upper()}_DATABASE",
    )

    configure_cmd.run(_args(target=str(tmp_path), store=None, verbose=False), None)

    assert len(recorder.snapshots) == 3
    final = (tmp_path / ".yak" / "deployment.yml").read_text()
    for snapshot in recorder.snapshots:
        assert snapshot == final
    assert (
        '"backend: postgres"' in final.replace("\n", "") or "backend: postgres" in final
    )


def test_command_aborts_on_first_provision_failure_and_keeps_deployment(
    tmp_path,
    monkeypatch,
):
    """The first failing store aborts non-zero; the written deployment stays."""
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    recorder = _RecordingRun(
        fail_at=2, deployment_file=tmp_path / ".yak" / "deployment.yml"
    )
    _patch_provision_run(monkeypatch, configure_cmd, recorder)
    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )
    monkeypatch.setattr(
        configure_cmd,
        "_ask_dsn",
        lambda store, default: f"env://{store.upper()}_DATABASE",
    )

    with pytest.raises(SystemExit):
        configure_cmd.run(_args(target=str(tmp_path), store=None, verbose=False), None)

    # provisioning stopped at the first failing store (runtime OK, contacts failed).
    assert len(recorder.calls) == 2
    # deployment.yml was written and persists with the final configuration.
    installation = load_installation(tmp_path / ".yak" / "deployment.yml")
    assert installation.binding_for("contacts").config == {
        "backend": "postgres",
        "dsn": "env://CONTACTS_DATABASE",
    }


def test_command_creates_a_missing_database_and_retries_provisioning(
    tmp_path, monkeypatch
):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    dsn = "postgresql://postgres:secret@localhost:5432/yakoon_provision_test"
    recorder = _ScriptedRun(
        [
            (1, _missing_stderr("yakoon_provision_test"), ""),  # provision fails: no DB
            (0, "", "created"),  # admin creates the database
            (0, "", ""),  # provisioning retry succeeds
        ],
        deployment_file=tmp_path / ".yak" / "deployment.yml",
    )
    _patch_provision_run(monkeypatch, configure_cmd, recorder)
    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )
    monkeypatch.setattr(configure_cmd, "_ask_dsn", lambda store, default: dsn)
    monkeypatch.setattr(configure_cmd, "_ask_create_database", lambda db: True)

    configure_cmd.run(
        _args(target=str(tmp_path), store="contacts", verbose=False), None
    )

    # The deployment was written before any provision attempt.
    assert len(recorder.snapshots) == 3
    installation = load_installation(tmp_path / ".yak" / "deployment.yml")
    assert installation.binding_for("contacts").config == {
        "backend": "postgres",
        "dsn": dsn,
    }
    # create database is invoked exactly once, then provisioning is retried.
    assert _admin_calls(recorder) == 1
    admin_call = next(c for c in recorder.calls if c[1:3] == ["-m", ADMIN_MODULE])
    assert admin_call[3] == dsn
    # two provisioning attempts total (initial + retry).
    provision_calls = [
        c for c in recorder.calls if c[1:3] == ["-m", "y5n.runtime.engine.provision"]
    ]
    assert len(provision_calls) == 2


def test_command_declining_database_creation_aborts_nonzero(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    recorder = _ScriptedRun(
        [(1, _missing_stderr("yakoon_provision_test"), "")],
        deployment_file=tmp_path / ".yak" / "deployment.yml",
    )
    _patch_provision_run(monkeypatch, configure_cmd, recorder)
    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )
    monkeypatch.setattr(
        configure_cmd,
        "_ask_dsn",
        lambda store, default: "postgresql://postgres:secret@localhost:5432/yakoon_provision_test",
    )
    monkeypatch.setattr(configure_cmd, "_ask_create_database", lambda db: False)

    with pytest.raises(SystemExit):
        configure_cmd.run(
            _args(target=str(tmp_path), store="contacts", verbose=False), None
        )

    # No admin operation, no retry; the deployment keeps the desired binding.
    assert _admin_calls(recorder) == 0
    assert len(recorder.calls) == 1
    installation = load_installation(tmp_path / ".yak" / "deployment.yml")
    assert installation.binding_for("contacts").config["backend"] == "postgres"


def test_command_create_database_failure_aborts_without_retry(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd
    from y5n.apps.yak.installation.deployment import load_installation

    _make_env(tmp_path)
    recorder = _ScriptedRun(
        [
            (1, _missing_stderr("yakoon_provision_test"), ""),  # provision fails
            (1, "permission denied to create database", ""),  # admin fails
        ],
        deployment_file=tmp_path / ".yak" / "deployment.yml",
    )
    _patch_provision_run(monkeypatch, configure_cmd, recorder)
    monkeypatch.setattr(
        configure_cmd, "_ask_backend", lambda store, binding: "postgres"
    )
    monkeypatch.setattr(
        configure_cmd,
        "_ask_dsn",
        lambda store, default: "postgresql://postgres:secret@localhost:5432/yakoon_provision_test",
    )
    monkeypatch.setattr(configure_cmd, "_ask_create_database", lambda db: True)

    with pytest.raises(SystemExit):
        configure_cmd.run(
            _args(target=str(tmp_path), store="contacts", verbose=False), None
        )

    # The admin operation ran once; provisioning was not retried.
    assert _admin_calls(recorder) == 1
    assert len(recorder.calls) == 2
    installation = load_installation(tmp_path / ".yak" / "deployment.yml")
    assert installation.binding_for("contacts").config["backend"] == "postgres"


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
    _venv_python(tmp_path)
    before = (tmp_path / ".yak" / "deployment.yml").read_text()
    captured: dict[str, str] = {}
    recorder = _RecordingRun(deployment_file=tmp_path / ".yak" / "deployment.yml")
    _patch_provision_run(monkeypatch, configure_cmd, recorder)

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
    # `yak configure <store>` re-provisions exactly that one store.
    assert len(recorder.calls) == 1
    assert "postgresql://prod/db" in recorder.calls[0][4]


def test_command_refuses_an_uninstalled_store(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd

    _make_env(tmp_path)
    before = (tmp_path / ".yak" / "deployment.yml").read_text()

    with pytest.raises(SystemExit) as exc:
        configure_cmd.run(
            _args(target=str(tmp_path), store="worlds", verbose=False), None
        )
    assert exc.value.code == 1

    assert (tmp_path / ".yak" / "deployment.yml").read_text() == before


def test_command_no_deployment_is_a_clean_fail(tmp_path, monkeypatch):
    from y5n.apps.yak.hosts.cli.commands import configure as configure_cmd

    monkeypatch.setattr(configure_cmd, "find_runtime_root", lambda: None)

    with pytest.raises(SystemExit) as exc:
        configure_cmd.run(
            _args(target=str(tmp_path / "empty"), store=None, verbose=False), None
        )
    assert exc.value.code == 1

    assert not (tmp_path / "empty" / ".yak" / "deployment.yml").exists()
