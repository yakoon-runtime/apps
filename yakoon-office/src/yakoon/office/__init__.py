from yakoon.base.plugins.plugin import PluginExport, PluginMeta
from yakoon.base.runtime.services import ServiceDirectory
from yakoon.office.controller import OfficeMailingCoreController

meta = PluginMeta(
    name="yakoon.office",
    version="0.1.0",
    description="Office ...",
)


def register(services: ServiceDirectory) -> PluginExport:

    return PluginExport(
        meta,
        controllers=[
            OfficeMailingCoreController,
        ],
    )
