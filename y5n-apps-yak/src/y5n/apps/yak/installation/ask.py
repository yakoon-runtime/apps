"""Interactive store assembly (ADR-19, open question #1).

`yak install` guides the operator through the store mapping: for every
declared store it asks which factory config materializes it. The asker
owns no knowledge — it only turns operator input into a backend choice
and a DSN.
"""

from __future__ import annotations

from rich.prompt import Prompt


class TerminalStoreAsker:
    """Ask the operator for the backend and DSN of a store."""

    def backend(self, store: str) -> str:
        return Prompt.ask(
            f"Backend for store '{store}'",
            choices=["memory", "postgres"],
            default="memory",
            show_choices=True,
        )

    def dsn(self, store: str, default: str) -> str:
        return Prompt.ask(
            f"DSN for store '{store}' (literal or env://NAME)",
            default=default,
        )
