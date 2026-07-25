"""Yakoon Platform Manager — CLI entry point."""

from __future__ import annotations

import sys

VERSION = "0.0.1"


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _show_help()
        return

    if args[0] in ("-V", "--version"):
        print(f"Yakoon Platform Manager {VERSION}")
        return

    print(f"Yakoon Platform Manager {VERSION}")
    print(f"Unknown command: {args[0]}")
    print()
    _show_help()


def _show_help() -> None:
    print(f"""Yakoon Platform Manager {VERSION}

Usage:
    yak <command> [options]

Commands:
    install     Install a Yakoon distribution
    create      Scaffold a new Yakoon project
    shell       Open an interactive Yakoon shell
    help        Show this help message

Resources:
    https://yakoon.org
""")
