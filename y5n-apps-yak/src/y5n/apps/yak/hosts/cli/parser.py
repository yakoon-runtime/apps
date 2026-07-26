from __future__ import annotations

import argparse


def _add_action(sub, name: str, actions: list[str], func):
    """Add a subparser with required action argument."""
    p = sub.add_parser(name, help="")
    p.add_argument("action", choices=actions, help="")
    p.add_argument("--path", "-p", help="Path to installation")
    p.set_defaults(func=func)


def build_parser() -> argparse.ArgumentParser:
    from y5n.apps.yak.hosts.cli.commands import bootstrap as _bootstrap
    from y5n.apps.yak.hosts.cli.commands import build as _build
    from y5n.apps.yak.hosts.cli.commands import doctor as _doctor
    from y5n.apps.yak.hosts.cli.commands import install as _install
    from y5n.apps.yak.hosts.cli.commands import resolve as _resolve
    from y5n.apps.yak.hosts.cli.commands import runtime as _runtime
    from y5n.apps.yak.hosts.cli.commands import shell as _shell
    from y5n.apps.yak.hosts.cli.commands import status as _status
    from y5n.apps.yak.hosts.cli.commands import update as _update
    from y5n.apps.yak.hosts.cli.commands import web as _web
    from y5n.apps.yak.hosts.cli.commands import workspace as _workspace

    parser = argparse.ArgumentParser(
        prog="yak",
        description="Yakoon Platform Manager",
        usage="yak <command> [options]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "  Installation\n"
            "    install            Install a distribution\n"
            "    update             Update an installation\n"
            "    status             Show installation status\n"
            "    doctor             Check installation health\n"
            "\n"
            "  Services\n"
            "    runtime start      Start the runtime\n"
            "    runtime stop       Stop the runtime\n"
            "    runtime status     Check if runtime is running\n"
            "    runtime restart    Restart the runtime\n"
            "\n"
            "  Interfaces\n"
            "    shell              Open the Yakoon shell\n"
            "    web start          Start the web server\n"
            "    web stop           Stop the web server\n"
            "    web status         Check web server status\n"
            "    web open           Open browser\n"
            "\n"
            "  Developer\n"
            "    bootstrap          Prepare this repository for development\n"
            "    resolve            Show resolved pack list\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("resolve", help="")
    p.add_argument("target")
    p.set_defaults(func=_resolve.run)

    p = sub.add_parser("install", help="Install an artifact or distribution")
    p.add_argument("artifact", help="Artifact or distribution name (e.g. dev, runtime, crm)")
    p.add_argument(
        "target", nargs="?", default=".",
        help="Target directory (default: current directory)",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed progress"
    )
    p.set_defaults(func=_install.run)

    p = sub.add_parser("status", help="")
    p.add_argument(
        "--path", "-p", help="Path to installation (default: current directory)"
    )
    p.set_defaults(func=_status.run)

    p = sub.add_parser("update", help="")
    p.add_argument("--path", "-p", help="Path to installation")
    p.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed progress"
    )
    p.set_defaults(func=_update.run)

    p = sub.add_parser("doctor", help="")
    p.add_argument("--path", "-p", help="Path to installation")
    p.set_defaults(func=_doctor.run)

    _add_action(sub, "runtime", ["start", "stop", "status", "restart"], _runtime.run)
    _add_action(sub, "web", ["start", "stop", "status", "open"], _web.run)

    p = sub.add_parser("build", help="Build an artifact from the current project")
    p.set_defaults(func=_build.run)

    p = sub.add_parser("bootstrap", help="Prepare this repository for development")
    p.set_defaults(func=_bootstrap.run)

    p = sub.add_parser("workspace", help="Manage Yakoon workspaces")
    ws_sub = p.add_subparsers(dest="ws_action", required=True, metavar="<action>")
    p_create = ws_sub.add_parser("create", help="Create a new workspace")
    p_create.add_argument("name", help="Workspace name")
    p_create.set_defaults(func=_workspace.run)

    p = sub.add_parser("shell", help="")
    p.add_argument("--path", "-p", help="Path to installation")
    p.set_defaults(func=_shell.run)

    return parser
