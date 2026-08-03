from y5n.runtime.engine.machine import RuntimeManager
from y5n.runtime.engine.settings import Settings
from y5n.runtime.engine.wire.runtime import build_runtime


async def create_runtime() -> RuntimeManager:

    settings = Settings()

    runtime = build_runtime(
        settings=settings,
    )

    return runtime
