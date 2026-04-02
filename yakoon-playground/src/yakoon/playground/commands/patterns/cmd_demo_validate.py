from yakoon.base.commands import Command, Request
from yakoon.base.flow import focus, receive
from yakoon.base.flow.patterns import write_text
from yakoon.base.flow.patterns.internal.validate import apply_errors, validate


class CmdDemoValidateSimple(Command):

    key = "demo.validate.simple"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")

        while True:
            yield focus(projection)

            event = yield receive()

            result = validate(projection, event, self.container)
            if not result.ok:
                projection = apply_errors(projection, result.errors)
                continue

            values = result.values
            yield write_text(f"Ihre Eingabe: {values}")
            break
