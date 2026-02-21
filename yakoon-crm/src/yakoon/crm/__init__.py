from yakoon.base.directories.service import ServiceDirectory
from yakoon.base.plugins.plugin import PluginExport, PluginMeta
from yakoon.crm.controller import CrmCustomerCoreController

meta = PluginMeta(
    name="yakoon.crm",
    version="0.1.0",
    description="CRM ...",
)


def register(services: ServiceDirectory) -> PluginExport:

    return PluginExport(
        meta,
        controllers=[
            CrmCustomerCoreController,
        ],
    )
