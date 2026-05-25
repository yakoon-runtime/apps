from yakoon.compose.demo_data import seed_demo_system_data
from yakoon.platform.machine import RuntimeHost
from yakoon.platform.runtime.bus import SessionBus
from yakoon.platform.wire.runtime import build_runtime, initialize_storage


async def create_runtime() -> RuntimeHost:

    engine = build_runtime(
        plugins=[
            "yakoon.shell",
            "yakoon.playground",
        ],
        capabilities={
            "audit": "default",
            "discovery": "default",
            "identity": "default",
            "interaction": "default",
            "jobs": "default",
            "workflow": "default",
        },
    )

    await initialize_storage(engine.container)
    await seed_demo_system_data(engine.container)

    bus = SessionBus()

    return RuntimeHost(
        engine=engine,
        bus=bus,
    )
