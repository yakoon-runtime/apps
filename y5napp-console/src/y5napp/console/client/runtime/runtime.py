from y5n.runtime.machine import RuntimeHost
from y5n.runtime.settings import Settings
from y5n.runtime.wire.runtime import build_runtime


async def create_runtime() -> RuntimeHost:

    settings = Settings()

    runtime = build_runtime(
        settings=settings,
        spaces=[
            "y5nspace.shell",
            "y5nspace.ident",
            "y5nspace.os",
            "y5nspace.runtime",
        ],
        capabilities={},
    )

    return runtime
