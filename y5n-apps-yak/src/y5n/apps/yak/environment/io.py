"""Read and write .yak/environment.yml — the environment's declaration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from y5n.apps.yak.pack.models import Mount

from .models import Environment

ENV_FILENAME = "environment.yml"


def env_path(context_root: Path) -> Path:
    return context_root / ".yak" / ENV_FILENAME


def touch(
    root: Path,
    *,
    name: str | None = None,
    install: dict[str, list[str]] | None = None,
    mounts: list[Mount] | None = None,
    workspace_path: str | None = None,
) -> Environment:
    """Load-or-create the environment, apply fields, stamp timestamps, save.

    This is the single write path for environment.yml: created stays from
    the first write, updated always advances. ``install`` replaces the
    declaration when given.
    """
    env = load(root) or Environment(name=name or root.name)
    now = datetime.now(UTC)
    env.created = env.created or now
    env.updated = now
    if name is not None:
        env.name = name
    if install is not None:
        env.install = install
    if mounts is not None:
        env.mounts = mounts
    if workspace_path is not None:
        env.workspace_path = workspace_path
    save(env, root)
    return env


def load(context_root: Path) -> Environment | None:
    path = env_path(context_root)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None
    install = data.get("install")
    # The old schema stored a resolved component list; it cannot express
    # the user's intent, so it is treated as absent (the install command
    # reports the clean break explicitly).
    if install is None:
        return None
    mounts = [
        Mount(source=m.get("source") or m.get("pack", ""), target=m["target"])
        for m in data.get("mounts", [])
    ]
    ws = data.get("workspace", {})
    inst = data.get("installation", {})
    return Environment(
        name=data.get("name", ""),
        schema=data.get("schema", "2"),
        install={
            str(k): [str(p) for p in (v or [])] for k, v in install.items()
        },
        mounts=mounts,
        workspace_path=(
            ws.get("path", "structure") if isinstance(ws, dict) else "structure"
        ),
        created=_parse_dt(inst.get("created")) if isinstance(inst, dict) else None,
        updated=_parse_dt(inst.get("updated")) if isinstance(inst, dict) else None,
    )


def _parse_dt(raw: str | None) -> datetime | None:
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return None


def save(env: Environment, context_root: Path) -> None:
    path = env_path(context_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    mounts_yaml = [{"source": m.source, "target": m.target} for m in env.mounts]
    data = {
        "schema": env.schema,
        "name": env.name,
        "install": {k: list(v) for k, v in env.install.items()},
        "workspace": {"path": env.workspace_path},
        "mounts": mounts_yaml,
    }
    if env.created or env.updated:
        inst = {}
        if env.created:
            inst["created"] = env.created.isoformat()
        if env.updated:
            inst["updated"] = env.updated.isoformat()
        data["installation"] = inst
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
