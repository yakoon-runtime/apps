from yakoon.compose.demo_data import seed_demo_system_data
from yakoon.compose.runtime import compose_runtime, initialize_storage
from yakoon.platform.machine import RuntimeHost
from yakoon.platform.runtime.bus import SessionBus


async def create_runtime() -> RuntimeHost:

    engine = compose_runtime(
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
