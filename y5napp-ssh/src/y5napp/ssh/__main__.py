import asyncio

from .app import run

try:
    asyncio.run(run())
except KeyboardInterrupt:
    pass
