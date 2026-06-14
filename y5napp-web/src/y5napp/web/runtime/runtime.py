from y5n.runtime.machine import RuntimeHost
from y5n.runtime.settings import RuntimeSettings, Settings
from y5n.runtime.wire.runtime import build_runtime


async def create_runtime() -> RuntimeHost:

    settings = Settings(
        runtime=RuntimeSettings(
            spaces=[
                "y5nspace.shell",
                "y5nspace.ident",
            ],
        )
    )

    host = build_runtime(
        capabilities={},
        settings=settings,
    )

    await host.setup()

    return host
