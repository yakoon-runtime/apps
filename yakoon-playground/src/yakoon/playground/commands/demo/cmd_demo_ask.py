from yakoon.base.commands import Command, Request
from yakoon.base.flow import ask, receive, write


class CmdDemoAskSimple(Command):

    key = "demo.ask.simple"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        yield ask(view)

        event = yield receive()

        value = event.require("result")
        yield write(f"Ihre Eingabe: {value}")


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
