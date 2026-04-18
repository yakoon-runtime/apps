class TerminalSurface:

    def __init__(self, max_views=50):
        self.max_views = max_views
        self.views = []
        self._view_start = 0
        self.buffer = None
        self.app = None

    def attach(self, buffer, app):
        self.buffer = buffer
        self.app = app

    def new_view(self):

        if not self.buffer:
            return

        # neue View beginnt oben
        self.buffer.cursor_position = 0
        self.buffer.insert_text("\n", move_cursor=False)

        # ---- LIMIT ----
        if len(self.views) > self.max_views:
            self.views.pop()
            self._render()

        self._view_start = 0

        self.views.insert(0, [])

    def write(self, text):

        if not self.views:
            self.new_view()

        self.views[0].append(text)

        self.buffer.cursor_position = self._view_start
        self.buffer.insert_text(text)

        self._view_start += len(text)

        if self.app:
            self.app.invalidate()

    def _render(self):

        doc = ""

        for view in self.views:
            doc += "\n" + "".join(view)

        self.buffer.text = doc
        self.buffer.cursor_position = 0

        if self.app:
            self.app.invalidate()
