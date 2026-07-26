"""yak status [<target>] — show installation status."""

from __future__ import annotations

from pathlib import Path

from y5n.apps.yak.hosts.cli.cwd import find_installation_path


def run(args, mgr) -> None:
    path = _resolve_path(args)
    if path is None:
        print("Not inside a Yak installation.")
        print("cd into an installation directory or pass one.")
        return

    state = path / ".yak" / "state.toml"
    marker = path / ".yak" / "installation.yml"

    if state.exists():
        inst = mgr.load(path)
        if inst is not None:
            _show(inst)
            return

    if marker.exists():
        _show_marker(marker)
        return

    print("Not a valid Yak installation.")


def _resolve_path(args) -> Path | None:
    target = args.target
    if target and target != ".":
        return Path(target).resolve()
    return find_installation_path()


def _show(inst) -> None:
    print(f"  {inst.name}")
    print(f"    distribution: {inst.distribution}")
    print(f"    status: {inst.status.value}")
    print(f"    packs: {', '.join(inst.packs)}")


def _show_marker(path: Path) -> None:
    import yaml

    data = yaml.safe_load(path.read_text())
    print(f"  {data.get('distribution', '?')}")
    print(f"    created: {data.get('created', '?')}")
    deps = data.get("artifacts", [])
    print(f"    artifacts: {', '.join(deps)}")
