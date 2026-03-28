from yakoon.base.flow import apply_errors, ask, text, validate
from yakoon.base.runtime.commands import Command, Request


class CmdDemoAskValidateSimple(Command):

    key = "demo.ask.validate"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        while True:
            event = yield ask(view)

            result = validate(view, event, self.services)
            if not result.ok:
                view = apply_errors(view, result.errors)
                continue

            values = result.values
            yield text(f"Ihre Eingabe: {values}")
            break
