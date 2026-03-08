from yakoon.base.plugins.module import ModuleExport, ModuleMeta
from yakoon.base.runtime.services import ServiceDirectory
from yakoon.office.controller import OfficeMailingCoreController

meta = ModuleMeta(
    name="yakoon.office",
    version="0.1.0",
    description="Office ...",
)


def register(services: ServiceDirectory) -> ModuleExport:

    return ModuleExport(
        meta,
        controllers=[
            OfficeMailingCoreController,
        ],
    )
