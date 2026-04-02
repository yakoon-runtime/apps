from yakoon.base.commands import Command, Request
from yakoon.base.flow import present


class CmdDemoPresent(Command):

    key = "demo.present.simple"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")
        yield present(projection)
