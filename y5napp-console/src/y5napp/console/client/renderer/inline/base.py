class BaseInlineRenderer:

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        raise NotImplementedError


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
