"""The yak usage text — single source for the bare command and --help."""

USAGE = """\
Usage:
    yak <command> [options]

  Getting started
    init                   Create a Yak context

  Typical workflow
    create → build → install → add → shell

  Development
    create pack            Create a new pack
    create command         Add a command to the current pack
    bootstrap              Prepare this repository for development

  Packaging
    build                  Build artifacts
    publish                Publish an artifact to the local store
    deploy                 Make a published artifact available in a repository

  Installation
    install                Create the minimal Yakoon platform
    add                    Add a pack or artifact
    update                 Update the installation

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
