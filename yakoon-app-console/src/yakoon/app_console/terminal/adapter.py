class PromptToolkitTerminal:

    def __init__(self, ui):
        self.ui = ui

    async def run(self):
        await self.ui.run()

    async def stop(self):
        await self.ui.stop()

    def set_prompt(self, field):
        self.ui.set_prompt(field)

    def reset_prompt(self):
        self.ui.reset_prompt()

    def write(self, text):
        self.ui.surface.write(text)
