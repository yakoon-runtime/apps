# Yakoon Apps

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)]()
[![Tests](https://github.com/yakoon-runtime/apps/actions/workflows/tests.yml/badge.svg)](https://github.com/yakoon-runtime/apps/actions/workflows/tests.yml)

**Status: Active development**

Host applications for Yakoon, sharing one repository.

## Applications

| App | Description | Entry |
| --- | ----------- | ----- |
| [`apps-yak`](apps-yak) | Tool / assembler — install, build, publish, deploy | `yak` |
| [`apps-runtime`](apps-runtime) | Runtime host application | `yakoon-runtime` |
| [`apps-shell`](apps-shell) | Interactive shell | `yakoon-shell` |
| [`apps-web`](apps-web) | Web frontend | `yakoon-web` |
| [`apps-console`](apps-console) | Terminal console | — |

Each application is its own Python package under `apps/`, with its own
pyproject and — where present — its own tests.

## Tests

The repository CI runs the `apps-yak` test suite (the only component with
tests today). See `apps-yak/README.md` for the CLI.

## Links

- Developer setup: [yakoon-runtime/developer](https://github.com/yakoon-runtime/developer)
- Runtime: [yakoon-runtime/runtime](https://github.com/yakoon-runtime/runtime)

## License

Apache 2.0. See [LICENSE](LICENSE).