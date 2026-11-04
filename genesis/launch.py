"""Launch the browser game, with an optional desktop companion, in one process."""
from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from genesis.pet.state import local_endpoint


def _show_pet(endpoint: str, smoke_test: bool) -> int:
    import tkinter as tk

    from genesis.pet.__main__ import Companion

    try:
        root = tk.Tk()
        state_path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GENESIS/companion.json"
        companion = Companion(root, endpoint, state_path)
        if smoke_test:
            root.after(1000, companion.close)
        root.mainloop()
        return 0
    except tk.TclError as error:
        print(f"Desktop unavailable: {error}. Run without --pet for the browser game.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the GENESIS browser game and local lab.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--anvil", default="anvil")
    parser.add_argument("--pet", action="store_true", help="also run the optional native desktop companion (requires Tk)")
    parser.add_argument("--no-browser", action="store_true", help="print the URL without opening a browser")
    parser.add_argument("--smoke-test", action="store_true",
                        help="check readiness, then exit (with --pet, close it after 1 second)")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    workspace = Path(__file__).resolve().parent.parent
    if not (workspace / "frontend/dist/index.html").is_file():
        print("Build the frontend first: npm --prefix frontend ci; npm --prefix frontend run build")
        return 1
    endpoint = local_endpoint(f"http://127.0.0.1:{args.port}")
    with socket.socket() as probe:
        occupied = probe.connect_ex(("127.0.0.1", args.port)) == 0
    server = None
    worker = None
    try:
        if not occupied:
            import uvicorn

            from genesis.lab.api import LabConfig, create_app

            config = LabConfig(scenarios_dir=workspace / "scenarios", anvil_executable=args.anvil,
                               static_dir=workspace / "frontend/dist")
            server = uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1", port=args.port,
                                                   log_level="warning"))
            worker = threading.Thread(target=server.run, daemon=True, name="genesis-lab")
            worker.start()
        # Readiness requests stay on loopback; do not follow redirects off-host.
        from urllib.request import HTTPRedirectHandler

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req: object, fp: object, code: int, msg: str,
                                 headers: object, newurl: str) -> None:
                return None

        opener = build_opener(ProxyHandler({}), NoRedirect())
        deadline = time.monotonic() + 40
        while True:
            try:
                with opener.open(endpoint + "/api/health", timeout=2) as response:
                    health = json.load(response)
                with opener.open(endpoint + "/api/mission", timeout=2) as response:
                    mission = json.load(response)
                if health.get("status") != "ready" or mission.get("scenario", {}).get("id") != "wrong-recipient":
                    raise ValueError("port is not serving a ready GENESIS lab")
                break
            except (OSError, ValueError) as error:
                if occupied or time.monotonic() >= deadline or (worker is not None and not worker.is_alive()):
                    print(f"Could not start a ready local lab: {error}. Check Anvil and port {args.port}.")
                    return 1
                time.sleep(.3)
        print(f"GENESIS ready. Game: {endpoint}; contract workshop: {endpoint}/#workshop")
        if not args.no_browser and not args.smoke_test:
            webbrowser.open(endpoint)
        if args.pet:
            return _show_pet(endpoint, args.smoke_test)
        if not args.smoke_test and worker is not None:
            print("Keep this terminal open. Press Ctrl+C to stop the local lab.")
            while worker.is_alive():
                worker.join(timeout=.5)
        return 0
    except ImportError as error:
        print(f"Missing optional desktop/lab dependency: {error}. Install .[lab,dev] and Python with Tk.")
        return 1
    except KeyboardInterrupt:
        print("GENESIS stopped.")
        return 0
    finally:
        if server is not None:
            server.should_exit = True
        if worker is not None:
            worker.join(timeout=8)


if __name__ == "__main__":
    raise SystemExit(main())
