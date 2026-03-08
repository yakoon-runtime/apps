from yakoon.base.plugins.module import ModuleExport, ModuleMeta
from yakoon.base.runtime.services import ServiceDirectory
from yakoon.crm.controller import CrmCustomerCoreController

meta = ModuleMeta(
    name="yakoon.crm",
    version="0.1.0",
    description="CRM ...",
)


def register(services: ServiceDirectory) -> ModuleExport:

    return ModuleExport(
        meta,
        controllers=[
            CrmCustomerCoreController,
        ],
    )
