from .base import BaseRenderer
from .inline import render_inline


class ParagraphRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        return render_inline(self.node.props["text"]) + "\n"
