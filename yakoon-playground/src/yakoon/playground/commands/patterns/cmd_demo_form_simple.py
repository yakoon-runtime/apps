from yakoon.base.commands import Command, Request
from yakoon.base.flow import receive
from yakoon.base.flow.patterns import form, write_text


class CmdDemoFormSimple(Command):

    key = "demo.form.simple"

    async def run(self, request: Request):

        projector = await self.create_projector()
        projection = await projector.project("view_1")

        yield form(projection, self.container, "form.receive")
        event = yield receive("form.receive")

        values = event.to_values()
        yield write_text(f"Ihre Eingabe: {values}")
