from .base import BaseRenderer


class SpacerRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        size = self.node.props.get("size", 1)
        return "\n" * size
