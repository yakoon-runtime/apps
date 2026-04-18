from yakoon.compose.demo_data import seed_demo_system_data
from yakoon.compose.engine import compose_engine, initialize_storage
from yakoon.platform.machine import RuntimeHost
from yakoon.platform.runtime.bus import SessionBus


async def create_runtime() -> RuntimeHost:

    engine = compose_engine(
        plugins=[
            "yakoon.shell",
            "yakoon.crm",
            "yakoon.office",
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
