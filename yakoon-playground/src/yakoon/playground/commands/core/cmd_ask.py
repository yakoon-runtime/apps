from yakoon.base.runtime.commands import Command, Request


class CmdUseAsk(Command):

    key = "use_ask"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        event = yield self.op.ask(view)

        value = event.require("result")
        yield text(f"Ihre Eingabe: {value}")


# name = (yield ask(view1)).require("name")
# age  = (yield ask(view2)).require("age")
