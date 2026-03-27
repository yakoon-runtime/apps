from yakoon.base.runtime.commands import Command, Request
from yakoon.base.runtime.flow import ask, text


class CmdDemoAskSimple(Command):

    key = "demo.ask.simple"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        event = yield ask(view)

        value = event.require("result")
        yield text(f"Ihre Eingabe: {value}")


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
