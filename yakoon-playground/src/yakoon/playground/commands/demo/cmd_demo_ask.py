from yakoon.base.commands import Command, Request
from yakoon.base.flow import ask, receive, write


class CmdDemoAskSimple(Command):

    key = "demo.ask.simple"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")

        yield ask(projection)

        event = yield receive()

        value = event.require("result")
        yield write(f"Ihre Eingabe: {value}")


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
