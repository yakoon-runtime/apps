from yakoon.base.commands import Command, Request
from yakoon.base.flow import ask, receive, write
from yakoon.base.flow.patterns.internal.validate import apply_errors, validate


class CmdDemoAskValidateSimple(Command):

    key = "demo.ask.validate"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")

        while True:
            yield ask(projection)

            event = yield receive()

            result = validate(projection, event, self.container)
            if not result.ok:
                projection = apply_errors(projection, result.errors)
                continue

            values = result.values
            yield write(f"Ihre Eingabe: {values}")
            break
