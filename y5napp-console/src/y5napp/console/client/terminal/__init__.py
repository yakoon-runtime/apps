from .base import Terminal
from .simple import SimpleTerminal
from .ssh import SSHTerminal


def PromptToolkitTerminal(*args, **kwargs):
    from .prompt import PromptToolkitTerminal as _PTK

    return _PTK(*args, **kwargs)


__all__ = [
    "PromptToolkitTerminal",
    "SimpleTerminal",
    "Terminal",
    "SSHTerminal",
]
