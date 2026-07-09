from __future__ import annotations

from rich.text import Text
from y5n.base.projection.model.inline import (
    Inline,
    InlineArg,
    InlineBreak,
    InlineCmd,
    InlineCode,
    InlineEm,
    InlineLink,
    InlineMark,
    InlineSelect,
    InlineSpace,
    InlineStrong,
    InlineText,
    InlineUnderline,
)


def render(inlines: list[Inline]) -> Text:
    result = Text()
    for node in inlines:
        _render_inline(result, node)
    return result


def _render_inline(result: Text, node: Inline) -> None:
    match node:
        case InlineText(text=t):
            result.append(t)
        case InlineCode():
            result.append(_stylize(node.children, "bold green"))
        case InlineStrong():
            result.append(_stylize(node.children, "bold"))
        case InlineEm():
            result.append(_stylize(node.children, "italic"))
        case InlineUnderline():
            result.append(_stylize(node.children, "underline"))
        case InlineLink(href=h):
            result.append(_stylize(node.children, f"link {h}"))
        case InlineArg():
            result.append(_stylize(node.children, "yellow"))
        case InlineMark(variant=v):
            result.append(_stylize(node.children, _mark_style(v)))
        case InlineCmd(command=cmd, variant=v):
            result.append(_stylize(node.children, _cmd_style(v)))
        case InlineSelect(value=val):
            result.append(str(val), style="magenta")
        case InlineBreak(count=n):
            result.append("\n" * (n or 1))
        case InlineSpace(count=n):
            result.append(" " * (n or 1))
        case _:
            result.append(f"<?{type(node).__name__}>")


def _children(children: list[Inline] | None) -> Text:
    result = Text()
    if children:
        for child in children:
            _render_inline(result, child)
    return result


def _stylize(children: list[Inline] | None, style: str) -> Text:
    text = _children(children)
    text.stylize(style)
    return text


def _mark_style(variant: str | None) -> str:
    match variant:
        case "highlight":
            return "yellow on #333"
        case "error":
            return "white on red"
        case "success":
            return "green on #0a0"
        case "warning":
            return "yellow on #330"
        case _:
            return "reverse"


def _cmd_style(variant: str | None) -> str:
    match variant:
        case "global":
            return "dim italic"
        case "container":
            return "bold italic"
        case _:
            return "bold"
