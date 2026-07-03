from .app import TextualApp
from .conf import load_config


def main() -> None:
    cfg, cfg_path = load_config()
    app = TextualApp(config=cfg, config_path=cfg_path)
    app.run()


if __name__ == "__main__":
    main()
