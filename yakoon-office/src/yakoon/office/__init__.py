from yakoon.base.plugins.module import ModuleExport, ModuleMeta
from yakoon.base.runtime import Container
from yakoon.office.controller import OfficeMailingCoreController

meta = ModuleMeta(
    name="yakoon.office",
    version="0.1.0",
    description="Office ...",
)


def register(container: Container) -> ModuleExport:

    return ModuleExport(
        meta,
        controllers=[
            OfficeMailingCoreController,
        ],
    )
