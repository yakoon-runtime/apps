"""Start the web client.

Usage:
    python -m y5napp.web                 # port from config
    python -m y5napp.web 8001            # override port
"""

import sys

from .conf import load_config
from .server import serve


def main() -> None:
    cfg = load_config()
    host = cfg.server.host if cfg.server else "127.0.0.1"
    port = int(sys.argv[1]) if len(sys.argv) > 1 else (cfg.server.port if cfg.server else 8000)
    runtime_url = cfg.runtime.url if cfg.runtime else "ws://localhost:9100"

    server = serve(host=host, port=port, runtime_url=runtime_url, config=cfg)
    print(flush=True)
    print("Ready.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(flush=True)
        print("Stopping web client...", flush=True)
        server.server_close()
        print("Done.", flush=True)


if __name__ == "__main__":
    main()
