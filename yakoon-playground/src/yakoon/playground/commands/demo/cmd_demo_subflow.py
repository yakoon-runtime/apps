from yakoon.base.commands import Command, Request
from yakoon.base.flow.dsl import ask, write


class CmdDemoSubflow(Command):

    key = "demo.subflow"

    async def run(self, request: Request):

        yield write("\nA start")
        yield self.sub()
        yield write("\nA end")
        yield write("\nA start again")
        yield self.sub()
        yield write("\nA end again")

    async def sub(self):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        yield write("\nB start")
        value = yield ask(view)
        yield write("\n" + f"B got {value}")


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
