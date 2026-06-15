"""Start the web client dev server.

Usage:
    python -m y5napp.web                 # port 8000
    python -m y5napp.web 8001            # custom port
"""

import sys

from .server import serve


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = serve(port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(flush=True)
        print("Stopping web client...", flush=True)
        server.server_close()
        print("Done.", flush=True)


if __name__ == "__main__":
    main()
