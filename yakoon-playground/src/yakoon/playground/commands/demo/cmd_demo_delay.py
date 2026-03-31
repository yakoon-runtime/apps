from yakoon.base.commands import Command, Request
from yakoon.base.flow import delay, present
from yakoon.base.projection.model import v_text


class CmdDemoDelay(Command):

    key = "demo.delay"

    async def run(self, request: Request):

        yield present(v_text("Start"))
        yield delay(5)
        yield present(v_text("\nDone"))
