from yakoon.base.commands import Command, Request
from yakoon.base.flow import present


class CmdDemoProjector(Command):

    key = "demo.projector"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")
        yield present(projection)
