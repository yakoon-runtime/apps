from yakoon.base.commands import Command, Request
from yakoon.base.flow.dsl import ask, text


class CmdDemoSubflow(Command):

    key = "demo.subflow"

    async def run(self, request: Request):

        yield text("\nA start")
        yield self.sub()
        yield text("\nA end")
        yield text("\nA start again")
        yield self.sub()
        yield text("\nA end again")

    async def sub(self):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        yield text("\nB start")
        value = yield ask(view)
        yield text("\n" + f"B got {value}")


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
