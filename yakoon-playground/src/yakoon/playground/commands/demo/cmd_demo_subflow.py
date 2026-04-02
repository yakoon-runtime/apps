from yakoon.base.commands import Command, Request
from yakoon.base.flow.dsl import ask, receive
from yakoon.base.flow.patterns import write_text


class CmdDemoSubflow(Command):

    key = "demo.subflow"

    async def run(self, request: Request):

        yield write_text("\nA start")
        yield self.sub()

        yield write_text("\nA end")
        yield write_text("\nA start again")

        yield self.sub()
        yield write_text("\nA end again")

    async def sub(self):

        projector = await self.create_projector()
        projection = await projector.project("view_1")

        yield write_text("\nB start")
        yield ask(projection)

        value = yield receive()
        yield write_text("\n" + f"B got {value}")


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
