"""The yak usage text — single source for the bare command and --help."""

USAGE = """\
Usage:
    yak <command> [options]

  Getting started
    init                   Create a Yak context

  Typical workflow
    create → build → install → sync → shell

  Development
    create pack            Create a new pack
    create command         Add a command to the current pack
    bootstrap              Prepare this repository for development

  Packaging
    build                  Build artifacts
    publish                Publish an artifact

  Environment
    install                Install a pack
    sync                   Sync workspace with environment

  Run
    shell                  Open the Yakoon shell
    runtime                Manage the runtime service
    web                    Manage the web service

  Tools
    status                 Show installation status
    mount                  Manage workspace mounts
    logs                   Show logs
    doctor                 Check installation health

Use 'yak <command> --help' for detailed options.
"""
