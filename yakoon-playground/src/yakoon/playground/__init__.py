from yakoon.base.plugins.module import ModuleExport, ModuleMeta
from yakoon.base.runtime import Container
from yakoon.playground.controller_dsl import DemoControllerDsl
from yakoon.playground.controller_patterns import DemoControllerPatterns

meta = ModuleMeta(
    name="yakoon.playground",
    version="0.1.0",
    description="playground ...",
)


def register(container: Container) -> ModuleExport:

    return ModuleExport(
        meta,
        controllers=[
            DemoControllerDsl,
            DemoControllerPatterns,
        ],
    )
