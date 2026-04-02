from yakoon.base.commands import Command, Request
from yakoon.base.flow import delay
from yakoon.base.flow.patterns import write_text


class CmdDemoDelaySimple(Command):

    key = "demo.delay.simple"

    async def run(self, request: Request):

        yield write_text("Start")

        yield delay(5)

        yield write_text("\nDone")
