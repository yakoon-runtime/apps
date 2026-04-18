from .base import BaseRenderer
from .inline import get_inline_text


class ListItemRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        value = self.node.props.get("text")
        text = get_inline_text(value)

        return f"• {text}\n"
