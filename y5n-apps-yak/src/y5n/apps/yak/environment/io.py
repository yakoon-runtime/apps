"""Read and write .yak/environment.yml."""

from __future__ import annotations

from pathlib import Path

import yaml
from y5n.apps.yak.distribution.models import Mount, PackName

from .models import Environment

ENV_FILENAME = "environment.yml"


def env_path(context_root: Path) -> Path:
    return context_root / ".yak" / ENV_FILENAME


def load(context_root: Path) -> Environment | None:
    path = env_path(context_root)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
        mounts = [
            Mount(pack=PackName(m["pack"]), target=m["target"])
            for m in data.get("mounts", [])
        ]
        deps = [PackName(d) for d in data.get("dependencies", [])]
        ws = data.get("workspace", {})
        return Environment(
            name=data.get("name", ""),
            schema=data.get("schema", "1"),
            dependencies=deps,
            mounts=mounts,
            workspace_path=(
                ws.get("path", "structure") if isinstance(ws, dict) else "structure"
            ),
        )
    except Exception:
        return None


def save(env: Environment, context_root: Path) -> None:
    path = env_path(context_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    mounts_yaml = [{"pack": m.pack, "target": m.target} for m in env.mounts]
    data = {
        "schema": env.schema,
        "name": env.name,
        "dependencies": list(env.dependencies),
        "workspace": {"path": env.workspace_path},
        "mounts": mounts_yaml,
    }
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def from_template(template_path: Path) -> Environment:
    """Read a template artifacts/*.yml and convert to Environment."""
    from y5n.apps.yak.distribution.models import Mount, PackName

    data = yaml.safe_load(template_path.read_text()) or {}
    ws = data.get("workspace", {})
    mounts = [
        Mount(pack=PackName(m["pack"]), target=m["target"])
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
