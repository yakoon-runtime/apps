from yakoon.base.commands import Command, Request
from yakoon.base.flow import receive, send
from yakoon.base.flow.patterns import write_text


class CmdDemSendSimple(Command):

    key = "demo.send.simple"

    async def run(self, request: Request):

        yield send("form.result", {"data": "flow"})

        r_event = yield receive("form.result")
        yield write_text(f"Ihre Eingabe: {r_event}")
