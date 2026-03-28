from yakoon.base.flow.dsl import ask, text
from yakoon.base.flow.primitives import Outcome
from yakoon.base.runtime.commands import Command, Request


class CmdDemoSubflow(Command):

    key = "demo.subflow"

    async def run(self, request: Request):

        result = yield self.ask_for_input("view_1")

        value = result.require("result")
        yield text(f"Ihre Eingabe: {value}")

    async def ask_for_input(self, view_name: str):
        presenter = await self.get_presenter()
        view = await presenter.render(view_name)

        event = yield ask(view)
        yield Outcome(value=event)


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
