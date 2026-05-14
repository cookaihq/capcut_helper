import uvicorn

from app.core.config import load_config
from app.core.port import select_port
from app.server import create_app


def main() -> None:
    cfg = load_config()
    port = select_port(cfg.port_range)
    app = create_app(port)
    print(f"capcut_helper backend running on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
