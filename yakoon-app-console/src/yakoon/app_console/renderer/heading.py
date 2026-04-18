from .base import BaseRenderer
from .inline import render_inline


class HeadingRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        level = self.node.props.get("level", 1)
        text = render_inline(self.node.props.get("text") or [])

        prefix = "#" * level
        return f"{prefix} {text}\n"
