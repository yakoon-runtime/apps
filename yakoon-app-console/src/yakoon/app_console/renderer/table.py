from .base import BaseRenderer


class TableRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:

        headers = self.node.props.get("headers") or []
        rows = self.node.props.get("rows") or []

        lines = []

        if headers:
            lines.append(" | ".join(headers))
            lines.append("-" * len(lines[0]))

        for row in rows:
            lines.append(" | ".join(row))

        return "\n".join(lines)
