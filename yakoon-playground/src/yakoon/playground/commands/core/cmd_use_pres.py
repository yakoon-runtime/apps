from yakoon.base.runtime.commands import Command, Request


class CmdUsePresenter(Command):

    key = "use_pres"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")
        yield show(view)
