from yakoon.base.commands import Command, Request
from yakoon.base.flow import receive
from yakoon.base.flow.patterns import confirm, write_text


class CmdDemoConfirmSimple(Command):

    key = "demo.confirm.simple"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")

        while True:
            yield confirm(projection, "confirm.channel", yes={"ja"}, no={"nein"})
            anser = yield receive("confirm.channel")

            yield write_text(f"Ihre Antwort: {anser}")
