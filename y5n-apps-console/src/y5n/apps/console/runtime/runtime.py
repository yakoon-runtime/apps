from pathlib import Path

import yaml
from y5n.apps.yak.installation.assemble import (
    build_memory_installation,
    collect_declared_stores,
)
from y5n.runtime.engine.installation import to_dict
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
    installation = build_memory_installation(stores)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(to_dict(installation), sort_keys=False))


async def create_runtime() -> RuntimeManager:

    structure_dir = Path.cwd() / "structure"
    installation_path = Path.cwd() / ".yak" / "installation" / "deployment.yml"

    # Respect an existing installation (ADR-19: owned by `yak`, machine
    # specific). Only a workspace without one gets the developer memory
    # fallback — the console never overwrites a real installation.
    if not installation_path.is_file():
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
