import os
import threading
import time
import argparse
import webbrowser

import uvicorn

TOOL_CALL_ADAPTER_HOST = os.getenv("TOOL_CALL_ADAPTER_HOST", "0.0.0.0")
TOOL_CALL_ADAPTER_PORT = int(os.getenv("TOOL_CALL_ADAPTER_PORT", "8000"))
OPEN_GUI_ON_START = os.getenv("OPEN_GUI_ON_START") not in (None, "0", "false", "False")


def _open_browser_once(delay: float, host: str, port: int):
    def target():
        time.sleep(delay)
        url = f"http://{host if host not in ('0.0.0.0','::') else '127.0.0.1'}:{port}/ui"
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            pass
    threading.Thread(target=target, daemon=True).start()


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Launch Native Tool Call Adapter server.")
    parser.add_argument("--host", default=TOOL_CALL_ADAPTER_HOST, help="Host to bind")
    parser.add_argument("--port", type=int, default=TOOL_CALL_ADAPTER_PORT, help="Port to bind")
    parser.add_argument("--open-gui", action="store_true", help="Open browser to /ui after start")
    args = parser.parse_args(argv)

    if OPEN_GUI_ON_START or args.open_gui:
        # Slight delay to allow server to come up
        _open_browser_once(0.8, args.host, args.port)

    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
