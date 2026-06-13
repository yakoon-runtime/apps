from y5n.compose.demo_data import seed_demo_system_data
from y5n.runtime.machine import RuntimeHost
from y5n.runtime.runtime.bus import SessionBus
from y5n.runtime.wire.runtime import build_runtime, initialize_storage


async def create_runtime() -> RuntimeHost:

    engine = build_runtime(
        spaces=[
            "y5n.shell",
            "y5n.playground",
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
