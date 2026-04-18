import asyncio

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from yakoon.base.projection.model import Field
from yakoon.base.runtime import InputEvent


class TerminalUI:

    def __init__(self, surface, on_cancel, on_submit):
        self.surface = surface
        self.on_cancel = on_cancel
        self.on_submit = on_submit

        self._prompt = "shell$ "
        self._current_field: Field | None = None
        self._has_errors = False

        self.history = InMemoryHistory()

        # ------------------------
        # Output View
        # ------------------------

        self.view = TextArea(
            text="",
            scrollbar=True,
            focusable=True,
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
            history=self.history,
        )
        self.shell.accept_handler = self._on_enter

        # ------------------------
        # Error Area (conditional)
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
            if self.on_cancel:
                asyncio.create_task(self.on_cancel())

        # ------------------------
        # Layout
        # ------------------------

        root = HSplit(
            [
                self.shell,
                # nur sichtbar bei Fehlern
                self.error_container,
                Window(height=1, char="─"),
                self.view,
            ]
        )

        self.app = Application(
            layout=Layout(root),
            full_screen=True,
            mouse_support=True,
            key_bindings=kb,
        )

        # styling
        self.style = Style.from_dict(
            {
                "": "#00d9ff bg:#000000",
                "prompt": "#00ffff bold",
                "cursor": "#ffffff reverse",
                "error": "#ff5f5f bold",
            }
        )
        # self.app.style = self.style

        self.surface.attach(self.view.buffer, self.app)

    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------

    async def run(self):
        await self.app.run_async()

    async def stop(self):
        if self.app.is_running:
            self.app.exit()

    # --------------------------------------------------------
    # Input Handling
    # --------------------------------------------------------

    def _on_enter(self, buffer):
        if not buffer.text:
            return

        text = buffer.text
        buffer.text = ""

        if self._current_field is None:
            self.surface.new_view()

        if self.on_submit:
            asyncio.create_task(self.on_submit(InputEvent.from_raw(text)))

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def add_history(self, command: str):
        self.history.append_string(command)

    # --------------------------------------------------------
    # Prompt + Errors
    # --------------------------------------------------------

    def set_prompt(self, field: Field):

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

    def reset_prompt(self):
        self._prompt = "shell$ "
        self._current_field = None
        self._has_errors = False
        self.errors.text = ""

        self.app.invalidate()

    def _update_errors(self, field: Field):

        if not field.errors:
            self._has_errors = False
            self.errors.text = ""
            return

        self._has_errors = True
        self.errors.text = "\n".join(f"{e.message}" for e in field.errors)
