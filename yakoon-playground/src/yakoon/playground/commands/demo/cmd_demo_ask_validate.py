from yakoon.base.commands import Command, Request
from yakoon.base.flow import ask, receive, write
from yakoon.base.flow.patterns.internal.validate import apply_errors, validate


class CmdDemoAskValidateSimple(Command):

    key = "demo.ask.validate"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")

        while True:
            yield ask(view)

            event = yield receive()

            result = validate(view, event, self.services)
            if not result.ok:
                view = apply_errors(view, result.errors)
                continue

            values = result.values
            yield write(f"Ihre Eingabe: {values}")
            break
