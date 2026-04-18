from .base import BaseRenderer


class SectionRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        return ""
