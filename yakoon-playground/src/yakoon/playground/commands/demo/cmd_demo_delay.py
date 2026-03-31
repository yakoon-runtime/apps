from yakoon.base.commands import Command, Request
from yakoon.base.flow import delay, show
from yakoon.base.projection import v_text


class CmdDemoDelay(Command):

    key = "demo.delay"

    async def run(self, request: Request):

        yield show(v_text("Start"))
        yield delay(5)
        yield show(v_text("\nDone"))
