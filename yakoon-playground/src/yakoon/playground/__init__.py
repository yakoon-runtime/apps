from yakoon.base.plugins.module import ModuleExport, ModuleMeta
from yakoon.base.runtime import Container
from yakoon.playground.controller import Demo1Controller

meta = ModuleMeta(
    name="yakoon.playground",
    version="0.1.0",
    description="playground ...",
)


def register(container: Container) -> ModuleExport:

    return ModuleExport(
        meta,
        controllers=[
            Demo1Controller,
        ],
    )
