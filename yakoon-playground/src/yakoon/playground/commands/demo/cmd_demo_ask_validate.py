from yakoon.base.commands import Command, Request
from yakoon.base.flow import write
from yakoon.base.flow.patterns import form


class CmdDemoAskValidateSimple(Command):

    key = "demo.ask.validate"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        result = yield form(view, self.services)

        values = result.values
        yield write(f"Ihre Eingabe: {values}")
