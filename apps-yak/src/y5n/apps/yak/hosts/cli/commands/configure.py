"""yak configure [<store>] — change the operator's deployment decisions.

`yak configure` walks the materialized store bindings of the deployment
(`.yak/deployment.yml`) and lets the administrator review each one —
memory → postgres, another dsn, ... Without an argument it walks every
bound store; with a store argument it configures exactly that one.
Existing values are the prompt defaults: pressing Enter keeps a binding's
current configuration, so the same command works as the initial setup and
as a later editor. Configuring never creates a store — need comes from
`yak install`.

After deployment.yml is persisted, the stores walked by this run are
provisioned through the installation venv (``<root>/.venv/bin/python -m
y5n.runtime.engine.provision <factory> <config>``) — every binding without
an argument, exactly the requested store with ``yak configure <store>``.
The first failing store aborts with a non-zero exit; the written
deployment stays as-is. `apps-yak` knows no backend details.

    yak configure            # walk all bound stores
    yak configure contacts   # configure a specific store directly
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from rich.prompt import Prompt
from y5n.apps.yak.hosts.cli.cwd import find_runtime_root
from y5n.apps.yak.hosts.cli.ui import TerminalUI
from y5n.apps.yak.installation.configure import (
    POSTGRES_BACKEND,
    configure_store,
    default_dsn,
    write_deployment,
)
from y5n.apps.yak.installation.deployment import Installation, load_installation
from y5n.apps.yak.installation.postgres import ensure_database


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))

    deployment_file = _find_deployment_file(
        Path(getattr(args, "target", ".")).resolve()
    )
    if deployment_file is None:
        ui.fail("No deployment found — run 'yak install' first")
        raise SystemExit(1)

    installation = load_installation(deployment_file)
    if installation is None or not installation.stores:
        ui.fail("The deployment binds no stores — run 'yak install' first")
        raise SystemExit(1)

    requested = getattr(args, "store", None)
    names = _resolve_names(installation, requested)
    if names is None:
        ui.fail(
            f"Store '{requested}' is not installed — configure never creates stores."
        )
        raise SystemExit(1)

    ui.title("Configuring stores")
    updated = installation
    for name in names:
        binding = updated.binding_for(name)
        current = (
            binding.config.get("backend", "?")
            if isinstance(binding.config, dict)
            else "?"
        )
        ui.text(f"Store: {name}")
        ui.text(f"Current backend: {current}")

        backend = _ask_backend(name, binding)
        dsn = None
        if backend == POSTGRES_BACKEND:
            dsn = _ask_dsn(name, default_dsn(binding, name))
            if not dsn:
                ui.fail(f"backend '{POSTGRES_BACKEND}' requires a dsn")
                raise SystemExit(1)
        updated = configure_store(updated, name, backend, dsn)

    write_deployment(updated, deployment_file)
    ui.ok("Configuration updated")
    _provision(updated, names, deployment_file, ui)
    ui.text("The changes take effect the next time the runtime starts.")


def _provision(
    installation: Installation,
    names: list[str],
    deployment_file: Path,
    ui,
) -> None:
    """Provision the configured store bindings in the installation venv.

    The stores walked by this run are provisioned — everything when the
    command ran without an argument, exactly the requested store when it
    ran as ``yak configure <store>``. `apps-yak` knows no backend details:
    each binding's factory and opaque config are handed to the engine's
    provisioning entrypoint, which runs with the installation's python.
    deployment.yml is already persisted (write-before-provision). The
    first failing store aborts with a non-zero exit; the written
    deployment stays as-is.

    When provisioning reports that the target database does not exist,
    the operator is asked interactively to create it (via the store's
    admin primitive) and provisioning is retried once.
    """
    python = deployment_file.parent.parent / ".venv" / "bin" / "python"
    if not python.is_file():
        ui.fail(f"No environment python at {python} — run 'yak install' first")
        raise SystemExit(1)

    for name in names:
        binding = installation.binding_for(name)
        if binding is None:
            continue
        config_json = (
            json.dumps(binding.config) if binding.config is not None else "null"
        )
        result = _provision_store(python, binding, config_json)
        if result.returncode == 0:
            ui.ok(f"Provisioning {name}")
            continue

        missing = _missing_database(result.stderr)
        if missing is None:
            ui.fail(f"Provisioning '{name}' failed:\n{result.stderr.strip()}")
            raise SystemExit(1)

        ui.text(f"Database '{missing}' does not exist.")
        if not _ask_create_database(missing):
            ui.fail(
                f"Store '{name}' cannot be provisioned — database '{missing}' "
                "does not exist."
            )
            raise SystemExit(1)

        dsn = binding.config.get("dsn") if isinstance(binding.config, dict) else None
        if not dsn:
            ui.fail(f"Store '{name}' has no dsn configured — cannot create database")
            raise SystemExit(1)

        ui.text(f"Creating database '{missing}' ...")
        try:
            ensure_database(deployment_file.parent.parent, dsn)
        except Exception as exc:
            ui.fail(f"Database '{missing}' could not be created:\n{exc}")
            raise SystemExit(1)
        ui.ok(f"Database '{missing}' created")

        result = _provision_store(python, binding, config_json)
        if result.returncode != 0:
            ui.fail(f"Provisioning '{name}' failed:\n{result.stderr.strip()}")
            raise SystemExit(1)
        ui.ok(f"Provisioning {name}")


def _provision_store(python: Path, binding, config_json: str):
    """Run the store factory's provisioning in the installation venv."""
    return subprocess.run(
        [
            str(python),
            "-m",
            "y5n.runtime.engine.provision",
            binding.factory,
            config_json,
        ],
        capture_output=True,
        text=True,
    )


_MISSING_DATABASE = re.compile(r'database "([^"]+)" does not exist')


def _missing_database(stderr: str) -> str | None:
    """The database name reported missing by the store, or None."""
    match = _MISSING_DATABASE.search(stderr or "")
    return match.group(1) if match else None


def _ask_create_database(database: str) -> bool:
    answer = Prompt.ask(
        f"Database '{database}' does not exist. Create it? [y/N]",
        default="n",
    )
    return answer.strip().lower() in ("y", "yes")


def _find_deployment_file(target: Path) -> Path | None:
    """Locate ``.yak/deployment.yml`` — in ``target`` or the nearest root."""
    direct = target / ".yak" / "deployment.yml"
    if direct.is_file():
        return direct
    found = find_runtime_root()
    if found is None:
        return None
    candidate = found / ".yak" / "deployment.yml"
    return candidate if candidate.is_file() else None


def _resolve_names(
    installation: Installation, requested: str | None
) -> list[str] | None:
    """The stores to configure — every binding, or exactly the requested one.

    ``None`` means the requested store is not installed: configure never
    creates a store.
    """
    if requested is None:
        return list(installation.stores)
    if requested in installation.stores:
        return [requested]
    return None


def _ask_backend(store: str, binding) -> str:
    current = (
        binding.config.get("backend")
        if isinstance(binding.config, dict)
        and binding.config.get("backend") in ("memory", "postgres")
        else "memory"
    )
    return Prompt.ask(
        f"Backend for store '{store}'",
        choices=["memory", "postgres"],
        default=current,
        show_choices=True,
    )


def _ask_dsn(store: str, default: str) -> str:
    return Prompt.ask(
        f"DSN for store '{store}' (literal or env://NAME)",
        default=default,
    )
