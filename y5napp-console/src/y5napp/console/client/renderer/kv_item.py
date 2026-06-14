from .base import BaseRenderer
from .inline import render_inline


class KVItemRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        key = self.node.props["key"]
        value = render_inline(self.node.props["value"])

        return f"{key}: {value}\n"
