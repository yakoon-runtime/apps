from __future__ import annotations

import argparse


def _add_action(sub, name: str, actions: list[str], func):
    p = sub.add_parser(name, help="")
    p.add_argument("action", choices=actions, help="")
    p.add_argument("--environment", "-e", help="Path to environment.yml file")
    p.set_defaults(func=func)


def build_parser() -> argparse.ArgumentParser:
    from y5n.apps.yak.hosts.cli.commands import build as _build
    from y5n.apps.yak.hosts.cli.commands import create_cap as _create_cap
    from y5n.apps.yak.hosts.cli.commands import create_command as _create_command
    from y5n.apps.yak.hosts.cli.commands import deploy as _deploy
    from y5n.apps.yak.hosts.cli.commands import doctor as _doctor
    from y5n.apps.yak.hosts.cli.commands import init_cmd as _init
    from y5n.apps.yak.hosts.cli.commands import install as _install
    from y5n.apps.yak.hosts.cli.commands import logs as _logs
    from y5n.apps.yak.hosts.cli.commands import mount as _mount
    from y5n.apps.yak.hosts.cli.commands import publish as _publish
    from y5n.apps.yak.hosts.cli.commands import runtime as _runtime
    from y5n.apps.yak.hosts.cli.commands import shell as _shell
    from y5n.apps.yak.hosts.cli.commands import status as _status
    from y5n.apps.yak.hosts.cli.commands import update as _update
    from y5n.apps.yak.hosts.cli.commands import web as _web
    from y5n.apps.yak.hosts.cli.commands import workspace as _workspace
    from y5n.apps.yak.hosts.cli.usage import USAGE

    parser = argparse.ArgumentParser(
        prog="yak",
        description="Yakoon Platform Manager",
        usage="yak <command> [options]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE,
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("init", help="Create a Yak context")
    p.add_argument(
        "target", nargs="?", default=".", help="Target directory (default: .)"
    )
    p.set_defaults(func=_init.run)

    p = sub.add_parser(
        "install",
        help="Compose an environment from a component or bundle (releases)",
    )
    p.add_argument("identity", help="Component or bundle name (e.g. runtime, crm)")
    p.add_argument(
        "--path",
        action="append",
        default=None,
        metavar="CATALOG",
        help="Local catalog source (repeatable, preferred)",
    )
    p.add_argument(
        "--target", "-t", default=".", help="Target directory (default: current)"
    )
    p.add_argument(
        "--distribution",
        metavar="URL",
        help="Distribution index URL to resolve against",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=_install.run)

    p = sub.add_parser("update", help="Update the installation")
    p.add_argument(
        "--target", "-t", default=".", help="Installation directory (default: current)"
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=_update.run)

    p = sub.add_parser("status", help="Show installation status")
    p.set_defaults(func=_status.run)

    p = sub.add_parser("mount", help="Manage workspace mounts")
    mount_sub = p.add_subparsers(dest="mount_action", required=True)
    p_add = mount_sub.add_parser("add", help="Add a mount")
    p_add.add_argument("source", help="Source directory path")
    p_add.add_argument(
        "--target", "-t", help="Target path in workspace (default: /<dirname>)"
    )
    p_add.set_defaults(func=_mount.run_add)
    p_rm = mount_sub.add_parser("remove", help="Remove a mount")
    p_rm.add_argument("target", help="Target path to remove")
    p_rm.set_defaults(func=_mount.run_remove)
    p_ls = mount_sub.add_parser("list", help="List mounts")
    p_ls.set_defaults(func=_mount.run_list)

    p = sub.add_parser("doctor", help="Check installation health")
    p.set_defaults(func=_doctor.run)

    p = sub.add_parser("logs", help="Show installation logs")
    p.add_argument("target", nargs="?", help="Log name (e.g. 'runtime', 'shell')")
    p.set_defaults(func=_logs.run)

    _add_action(sub, "runtime", ["start", "stop", "status", "restart"], _runtime.run)
    _add_action(sub, "web", ["start", "stop", "status", "open"], _web.run)

    p = sub.add_parser("shell", help="Open the Yakoon shell")
    p.set_defaults(func=_shell.run)

    p = sub.add_parser(
        "publish", help="Publish a bundle's artifacts to the local store"
    )
    p.add_argument(
        "name", help="Bundle or component name (e.g. runtime, y5n-packs-hello)"
    )
    p.set_defaults(func=_publish.run)

    p = sub.add_parser(
        "deploy",
        help="Deploy a published bundle to its owning repositories",
    )
    p.add_argument("name", help="Bundle or component name (e.g. runtime, crm)")
    p.add_argument(
        "--to",
        help="Repository spec (e.g. github:owner/repo) — overrides the "
        "component's own distribution",
    )
    p.set_defaults(func=_deploy.run)

    p = sub.add_parser(
        "build", help="Build a bundle's artifacts from source into the current context"
    )
    p.add_argument(
        "source",
        nargs="?",
        help="Bundle or source path (e.g. runtime, ./runtime/packages/runtime-engine)",
    )
    p.set_defaults(func=_build.run)

    p = sub.add_parser("create", help="Scaffold new Yakoon projects")
    create_sub = p.add_subparsers(dest="create_action", required=True)
    p_cap = create_sub.add_parser("cap", help="Create a new cap")
    p_cap.add_argument("name", help="Cap name (e.g. hello)")
    p_cap.add_argument("--target", help="Target directory (default: CWD)")
    p_cap.add_argument(
        "--force", "-f", action="store_true", help="Overwrite existing directory"
    )
    p_cap.set_defaults(func=_create_cap.run)
    p_cmd = create_sub.add_parser(
        "command", help="Create a new command in the current cap"
    )
    p_cmd.add_argument("name", help="Command name (e.g. greet)")
    p_cmd.add_argument("--cap", help="Cap name (auto-detected from CWD if omitted)")
    p_cmd.add_argument(
        "--force", "-f", action="store_true", help="Overwrite existing files"
    )
    p_cmd.set_defaults(func=_create_command.run)

    p = sub.add_parser("workspace", help="Manage Yakoon workspaces")
    ws_sub = p.add_subparsers(dest="ws_action", required=True)
    p_create = ws_sub.add_parser("create", help="Create a new workspace")
    p_create.add_argument("name")
    p_create.set_defaults(func=_workspace.run)

    return parser
