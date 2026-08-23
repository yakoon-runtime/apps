"""yak configure [<store>] — change the operator's deployment decisions.

`yak configure` reads the materialized deployment (`.yak/deployment.yml`)
and lets the administrator rebind existing stores — memory → postgres,
another dsn, ... It never creates a store: need comes from `yak install`.
The change takes effect the next time the runtime starts; there is no
automatic restart.

    yak configure            # list stores, then pick one
    yak configure contacts   # configure a specific store directly
"""

from __future__ import annotations

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


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))

    deployment_file = _find_deployment_file(
        Path(getattr(args, "target", ".")).resolve()
    )
    if deployment_file is None:
        ui.fail("No deployment found — run 'yak install' first")
        return

    installation = load_installation(deployment_file)
    if installation is None or not installation.stores:
        ui.fail("The deployment binds no stores — run 'yak install' first")
        return

    store = getattr(args, "store", None)
    if store is not None and store not in installation.stores:
        ui.fail(f"Store '{store}' is not installed — configure never creates stores.")
        return

    store = store or _select_store(installation, ui)
    binding = installation.binding_for(store)

    backend = _ask_backend(store, binding)
    dsn = None
    if backend == POSTGRES_BACKEND:
        dsn = _ask_dsn(store, default_dsn(binding, store))
        if not dsn:
            ui.fail(f"backend '{POSTGRES_BACKEND}' requires a dsn")
            return

    write_deployment(
        configure_store(installation, store, backend, dsn),
        deployment_file,
    )
    ui.ok(f"Configured store '{store}'")
    ui.text("The change takes effect the next time the runtime starts.")


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


def _select_store(installation: Installation, ui: TerminalUI) -> str:
    """Show the bound stores and let the operator pick one."""
    ui.text("Stores:")
    for name, binding in installation.stores.items():
        backend = (
            binding.config.get("backend", "?")
            if isinstance(binding.config, dict)
            else "?"
        )
        ui.text(f"  {name:<12} {backend}")
    return Prompt.ask("Select store", choices=list(installation.stores))


def _ask_backend(store: str, binding) -> str:
    current = (
        binding.config.get("backend")
        if isinstance(binding.config, dict)
        and binding.config.get("backend")
        in (
            "memory",
            "postgres",
        )
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
