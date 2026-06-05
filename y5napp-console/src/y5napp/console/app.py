import os

from y5n.runtime.transport import LocalTransport
from y5ncli.console.client.runtime import Client, create_runtime
from y5ncli.console.client.terminal import Terminal

TERMINALS = {}

try:
    from y5ncli.console.client.terminal import SimpleTerminal

    TERMINALS["simple"] = SimpleTerminal
except ImportError:
    pass

try:
    from y5ncli.textual import TextualTerminal

    TERMINALS["textual"] = TextualTerminal
except ImportError:
    pass


def _resolve_terminal(name: str) -> Terminal:
    try:
        cls = TERMINALS[name]
    except KeyError:
        available = ", ".join(TERMINALS)
        raise RuntimeError(
            f"Unknown terminal '{name}'. Available: {available}"
        ) from None
    return cls()


async def run() -> None:

    host = await create_runtime()
    await host.setup()

    transport = LocalTransport(host)

    name = os.environ.get("Y5N_TERMINAL", "textual")  # "simple")
    terminal = _resolve_terminal(name)
    client = Client(transport)

    await client.run(terminal)
