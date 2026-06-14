from .base import BaseRenderer
from .inline import render_inline


class HeadingRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        level = self.node.props["level"]
        text = render_inline(self.node.props["text"])

        prefix = "#" * level
        return f"{prefix} {text}\n"
