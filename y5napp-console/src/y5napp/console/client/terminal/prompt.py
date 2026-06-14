import asyncio

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.widgets import TextArea
from y5n.base.projection.model import Field

from .base import Terminal


class PromptToolkitTerminal(Terminal):

    def __init__(self):

        self._prompt = ""
        self._current_field: Field | None = None
        self._has_errors = False

        self.history = InMemoryHistory()

        # ------------------------
        # Output View
        # ------------------------

        self.view = TextArea(
            text="",
            scrollbar=True,
            focusable=False,
            wrap_lines=True,
        )

        # ------------------------
        # Input Shell
        # ------------------------

        self.shell = TextArea(
            height=1,
            prompt=lambda: self._prompt,
            multiline=False,
            wrap_lines=False,
            focusable=True,
            history=self.history,
        )

        self.shell.accept_handler = self._on_enter  # type: ignore

        # ------------------------
        # Error Area
        # ------------------------

        self.errors = TextArea(
            text="",
            height=1,
            focusable=False,
            wrap_lines=True,
            style="class:error",
        )

        self.error_container = ConditionalContainer(
            content=self.errors,
            filter=Condition(lambda: self._has_errors),
        )

        # ------------------------
        # Keybindings
        # ------------------------

        kb = KeyBindings()

        @kb.add("pageup")
        def _(event):
            self.view.buffer.cursor_up(count=5)

        @kb.add("pagedown")
        def _(event):
            self.view.buffer.cursor_down(count=5)

        @kb.add("c-c")
        def _(event):
            asyncio.create_task(self.stop())

        # ------------------------
        # Layout (FIXED)
        # ------------------------

        root = HSplit(
            [
                self.view,
                Window(height=1, char="─"),
                self.error_container,
                self.shell,
            ]
        )

        self.app = Application(
            layout=Layout(root),
            full_screen=True,
            mouse_support=True,
            key_bindings=kb,
        )

    # ------------------------
    # Terminal API
    # ------------------------

    async def run(self):
        await self.app.run_async()

    async def stop(self):
        if self.app.is_running:
            self.app.exit()

    async def on_input(self, text):
        """Wird vom Client gesetzt"""
        pass

    def write(self, text: str):
        self.view.buffer.insert_text(text)
        self.app.invalidate()

    def new_line(self):
        self.write("\n")

    def set_prompt(self, text: str):
        self._prompt = text
        self._current_field = None
        self._has_errors = False
        self.errors.text = ""

        self.app.invalidate()

    # --------------------------------------------------------
    # Input Handling
    # --------------------------------------------------------

    def _on_enter(self, buffer):
        if not buffer.text:
            return

        text = buffer.text
        buffer.text = ""

        if self.on_input:
            asyncio.create_task(self.on_input(text))

        return True

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def add_history(self, command: str):
        self.history.append_string(command)

    def set_field_prompt(self, field: Field):

        def format_label(field: Field) -> str:
            label = field.title or field.name or ""

            if field.required:
                return f"{label}:*"

            return f"{label}:"

        self._current_field = field

        label = format_label(field)
        value = field.value if field.value is not None else ""
        if value:
            label += f" >>{value}"

        self._prompt = label + " "

        self._update_errors(field)

        self.app.invalidate()

    def _update_errors(self, field: Field):

        if not field.errors:
            self._has_errors = False
            self.errors.text = ""
            return

        self._has_errors = True
        self.errors.text = "\n".join(f"{e.message}" for e in field.errors)
