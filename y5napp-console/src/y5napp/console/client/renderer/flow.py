from .base import BaseRenderer


class FlowRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        return ""
