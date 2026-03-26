from yakoon.base.api import Command, Request
from yakoon.base.api.flow import ask, text
from yakoon.base.runtime.steps.outcome import Outcome


class CmdSub(Command):

    key = "use_sub"

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
