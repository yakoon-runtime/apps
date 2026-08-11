"""yak install [<environment>] [--target <dir>] — create a Yakoon installation.

`yak install <environment>` installs the chosen environment into the
current directory; `--target` overrides the destination. The directory
name is not coupled to the environment name.
"""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.ui import TerminalUI


def run(args, mgr) -> None:
    ui = TerminalUI(verbose=getattr(args, "verbose", False))
    name = getattr(args, "environment", None)

    if not name:
        name = _select_environment(mgr)
        if name is None:
            return

    root = Path(getattr(args, "target", ".")).resolve()

    if _is_installed(root):
        ui.fail("Yakoon is already installed here — use 'yak add' or 'yak update'")
        return

    if mgr.is_development(name):
        ui.fail(
            f"'{name}' is a development environment.\n"
            "  Use 'yak bootstrap' to prepare the source repository."
        )
        return

    from y5n.apps.yak.installation.ask import TerminalStoreAsker

    ui.title(f'Installing "{name}"')
    try:
        mgr.install(name, root, asker=TerminalStoreAsker(), ui=ui)
        ui.ok(f"{name} ready at {root}")
    except Exception as e:
        ui.fail(f"Installation failed: {e}")


def _is_installed(root: Path) -> bool:
    """An installation marker (.yak/state.toml or environment.yml) exists."""
    yak = root / ".yak"
    return (yak / "state.toml").exists() or (yak / "environment.yml").exists()


def _select_environment(mgr) -> str | None:
    """List the available environments and let the operator pick one."""
    environments = mgr.list_environments()
    if not environments:
        print("  No environments available.")
        print("  Run 'yak build <source>' to build artifacts first.")
        return None

    print("  Available environments:")
    for name, desc in environments:
        desc_str = f"  — {desc}" if desc else ""
        print(f"    {name}{desc_str}")

    from rich.prompt import Prompt

    return Prompt.ask("Select environment", choices=[n for n, _ in environments])
