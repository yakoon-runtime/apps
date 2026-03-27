from yakoon.base.plugins.module import ModuleExport, ModuleMeta
from yakoon.base.runtime.services import ServiceDirectory
from yakoon.playground.controller import Demo1Controller

meta = ModuleMeta(
    name="yakoon.playground",
    version="0.1.0",
    description="playground ...",
)


def register(services: ServiceDirectory) -> ModuleExport:

    return ModuleExport(
        meta,
        controllers=[
            Demo1Controller,
        ],
    )
