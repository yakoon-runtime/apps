from __future__ import annotations

import argparse


def _add_action(sub, name: str, actions: list[str], func):
    p = sub.add_parser(name, help="")
    p.add_argument("action", choices=actions, help="")
    p.set_defaults(func=func)


def build_parser() -> argparse.ArgumentParser:
    from y5n.apps.yak.hosts.cli.commands import bootstrap as _bootstrap
    from y5n.apps.yak.hosts.cli.commands import build as _build
    from y5n.apps.yak.hosts.cli.commands import doctor as _doctor
    from y5n.apps.yak.hosts.cli.commands import artifacts as _artifacts
    from y5n.apps.yak.hosts.cli.commands import init_cmd as _init
    from y5n.apps.yak.hosts.cli.commands import install as _install
    from y5n.apps.yak.hosts.cli.commands import logs as _logs
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
            "\n"
            "  Getting started\n"
            "    init         [dir]     Create a Yak context in current or given directory\n"
            "\n"
            "  Development\n"
            "    build                  Build artifacts from the current project\n"
            "    bootstrap              Prepare this repository for development\n"
            "    workspace create <n>   Create a new workspace\n"
            "    resolve  <name>        Show resolved artifacts\n"
            "\n"
            "  Management\n"
            "    install <name>          Install a distribution\n"
            "    update                 Update an installation\n"
            "    status                 Show installation status\n"
            "    doctor                 Check installation health\n"
            "    artifacts      [name]   List artifacts or show details\n"
            "    logs         [name]    Show logs for the current context\n"
            "\n"
            "  Services\n"
            "    runtime <act>          Manage the runtime service\n"
            "    web     <act>          Manage the web service\n"
            "    shell                  Open the Yakoon shell\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("resolve", help="Show resolved artifacts")
    p.add_argument("name")
    p.set_defaults(func=_resolve.run)

    p = sub.add_parser("init", help="Create a Yak context")
    p.add_argument("target", nargs="?", default=".", help="Target directory (default: .)")
    p.set_defaults(func=_init.run)

    p = sub.add_parser("install", help="Install an artifact or distribution")
    p.add_argument("artifact")
    p.add_argument("target", nargs="?", default=".", help=argparse.SUPPRESS)
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=_install.run)

    p = sub.add_parser("status", help="Show installation status")
    p.set_defaults(func=_status.run)

    p = sub.add_parser("update", help="Update an installation")
    p.add_argument("--force", "-f", action="store_true", help="Force reinstall even if version is unchanged")
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=_update.run)

    p = sub.add_parser("doctor", help="Check installation health")
    p.set_defaults(func=_doctor.run)

    p = sub.add_parser("artifacts", help="List artifacts or show details")
    p.add_argument("name", nargs="?", help="Artifact name (shows details)")
    p.set_defaults(func=_artifacts.run)

    p = sub.add_parser("logs", help="Show installation logs")
    p.add_argument("target", nargs="?", help="Log name (e.g. 'runtime', 'shell')")
    p.set_defaults(func=_logs.run)

    _add_action(sub, "runtime", ["start", "stop", "status", "restart"], _runtime.run)
    _add_action(sub, "web", ["start", "stop", "status", "open"], _web.run)

    p = sub.add_parser("shell", help="Open the Yakoon shell")
    p.set_defaults(func=_shell.run)

    p = sub.add_parser("build", help="Build artifacts from source into the current context")
    p.add_argument("source", nargs="?", help="Source project path (default: current directory)")
    p.set_defaults(func=_build.run)

    p = sub.add_parser("bootstrap", help="Prepare this repository for development")
    p.set_defaults(func=_bootstrap.run)

    p = sub.add_parser("workspace", help="Manage Yakoon workspaces")
    ws_sub = p.add_subparsers(dest="ws_action", required=True)
    p_create = ws_sub.add_parser("create", help="Create a new workspace")
    p_create.add_argument("name")
    p_create.set_defaults(func=_workspace.run)

    return parser
