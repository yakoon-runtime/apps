from pathlib import Path

import yaml
from y5n.apps.yak.installation.assemble import collect_declared_stores
from y5n.runtime.engine.installation import (
    Deployment,
    Installation,
    StoreMapping,
    to_dict,
)
from y5n.runtime.engine.machine import RuntimeManager
from y5n.runtime.engine.settings import RuntimeSettings, Settings
from y5n.runtime.engine.wire.runtime import build_runtime


def _write_memory_installation(structure_dir: Path, target: Path) -> None:
    """Materialize a temporary memory installation for the developer host.

    The console is an embedded developer host — it is never installed by
    `yak`. It still needs an installation (ADR-19: no runtime without
    one), so it writes its own memory-backed deployment file next to the
    workspace.
    """
    stores = collect_declared_stores(structure_dir)
    installation = Installation(
        stores={name: StoreMapping(store=name, deployment="memory") for name in stores},
        deployments={
            "memory": Deployment(name="memory", backend="memory"),
        },
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(to_dict(installation), sort_keys=False))


async def create_runtime() -> RuntimeManager:

    structure_dir = Path.cwd() / "structure"
    installation_path = Path.cwd() / ".yak" / "installation" / "deployment.yml"

    _write_memory_installation(structure_dir, installation_path)

    settings = Settings(
        runtime=RuntimeSettings(
            workspace_path=str(structure_dir),
            installation_path=str(installation_path),
        )
    )

    runtime = build_runtime(
        settings=settings,
    )

    return runtime
