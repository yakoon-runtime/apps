from yakoon.base.runtime.commands import Command, Request
from yakoon.base.ui import v_text


class CmdDelay(Command):

    key = "delay_5"

    async def run(self, request: Request):

        yield show(v_text("Start"))
        yield delay(5)
        yield show(v_text("Done"))
