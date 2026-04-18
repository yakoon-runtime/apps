import asyncio

from .app import run

# ssh -p 8022 localhost
# ssh -T -p 8022 localhost  (ctrl-d)
# .

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
