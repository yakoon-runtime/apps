from .base import BaseRenderer
from .inline import render_inline


class ParagraphRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        value = self.node.props.get("text") or []
        return render_inline(value) + "\n"
