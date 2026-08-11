"""Read and write .yak/environment.yml."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from y5n.apps.yak.pack.models import Mount, PackName

from .models import Environment

ENV_FILENAME = "environment.yml"


def env_path(context_root: Path) -> Path:
    return context_root / ".yak" / ENV_FILENAME


def touch(
    root: Path,
    *,
    name: str | None = None,
    dependencies: list[PackName] | None = None,
    mounts: list[Mount] | None = None,
) -> Environment:
    """Load-or-create the environment, apply fields, stamp timestamps, save.

    This is the single write path for environment.yml during installs:
    created stays from the first write, updated always advances.
    """
    env = load(root) or Environment(name=name or root.name)
    now = datetime.now(UTC)
    env.created = env.created or now
    env.updated = now
    if dependencies is not None:
        env.dependencies = dependencies
    if mounts is not None:
        env.mounts = mounts
    save(env, root)
    return env


def load(context_root: Path) -> Environment | None:
    path = env_path(context_root)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
        mounts = [
            Mount(source=m.get("source") or m.get("pack", ""), target=m["target"])
            for m in data.get("mounts", [])
        ]
        deps = [PackName(d) for d in data.get("dependencies", [])]
        ws = data.get("workspace", {})
        inst = data.get("installation", {})
        return Environment(
            name=data.get("name", ""),
            schema=data.get("schema", "1"),
            dependencies=deps,
            mounts=mounts,
            workspace_path=(
                ws.get("path", "structure") if isinstance(ws, dict) else "structure"
            ),
            created=_parse_dt(inst.get("created")) if isinstance(inst, dict) else None,
            updated=_parse_dt(inst.get("updated")) if isinstance(inst, dict) else None,
        )
    except Exception:
        return None


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
        "dependencies": list(env.dependencies),
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


def from_template(template_path: Path) -> Environment:
    """Read a template artifacts/*.yml and convert to Environment."""
    from y5n.apps.yak.pack.models import Mount, PackName

    data = yaml.safe_load(template_path.read_text()) or {}
    ws = data.get("workspace", {})
    mounts = [
        Mount(source=m.get("source") or m.get("pack", ""), target=m["target"])
        for m in ws.get("mounts", [])
    ]
    deps = [PackName(d) for d in data.get("dependencies", [])]
    return Environment(
        name=data.get("name", "dev"),
        dependencies=deps,
        mounts=mounts,
        workspace_path=(
            ws.get("path", "structure") if isinstance(ws, dict) else "structure"
        ),
    )
