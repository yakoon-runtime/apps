from yakoon.base.commands import Command, Request
from yakoon.base.flow import focus, receive
from yakoon.base.flow.patterns import write_text


class CmdDemoFocusSimple(Command):

    key = "demo.focus.simple"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")

        yield focus(projection)

        event = yield receive()

        value = event.require("result")
        yield write_text(f"Ihre Eingabe: {value}")
