"""The yak usage text — single source for the bare command and --help."""

USAGE = """\
Usage:
    yak <command> [options]

  Getting started
    init                   Create a Yak context

  Typical workflow
    build → install → configure (optional) → shell

  Packaging
    build                  Build artifacts
    publish                Publish an artifact to the local store
    deploy                 Make a published artifact available in a repository

  Installation
    install                Compose an environment (component or bundle)
    update                 Update the installation
    configure              Change the deployment decision for an installed store

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
