from .base import BaseRenderer
from .inline import render_inline


class ListItemRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        value = self.node.props.get("text")
        text = render_inline(value)

        return f"• {text}\n"
