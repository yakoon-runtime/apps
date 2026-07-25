_factory = None


# ------------------------
# PUBLIC API
# ------------------------


def render_inline(value):

    if not value:
        return ""

    if isinstance(value, str):
        raise TypeError("\nExpected inline[], got str")

    factory = _get_factory()

    parts = []

    for inline in value:
        renderer = factory.create(inline)
        parts.append(renderer.render())

    return "".join(parts)


# ------------------------
# INTERNALS
# ------------------------

_factory = None


def _get_factory():
    global _factory
    if _factory is None:
        from .factory import InlineRendererFactory

        _factory = InlineRendererFactory()
    return _factory
