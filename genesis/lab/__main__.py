"""``python -m genesis.lab``: serve the Security Lab on a loopback address.

The server only binds to loopback. To reach it from another machine, use an
SSH tunnel or a reverse proxy with authentication (see docs/SECURITY_LAB.md),
never a public bind.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_STATIC = Path("frontend") / "dist"


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m genesis.lab", description="Serve the GENESIS Security Lab.")
    parser.add_argument("--host", default="127.0.0.1", help="loopback address to bind (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8000, help="port (default: %(default)s)")
    parser.add_argument("--anvil", default="anvil", help="anvil executable (default: found on PATH)")
    parser.add_argument("--rpc-url", default=None, help="use a running local Anvil node instead of starting one")
    parser.add_argument("--scenarios", default="scenarios", help="scenario directory (default: %(default)s)")
    parser.add_argument("--static", default=None, help=f"built frontend to serve (default: {DEFAULT_STATIC} if built)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not _loopback(args.host):
        print(f"error: refusing to bind {args.host}: the lab is a single-user local service", file=sys.stderr)
        return 1
    try:
        import uvicorn

        from genesis.lab.api import LabConfig, create_app
    except ImportError as missing:
        print(f"error: {missing}. Install the lab extra: uv pip install -e .[lab]", file=sys.stderr)
        return 1
    static = Path(args.static) if args.static else (DEFAULT_STATIC if (DEFAULT_STATIC / "index.html").is_file() else None)
    config = LabConfig(
        scenarios_dir=Path(args.scenarios),
        anvil_executable=args.anvil,
        rpc_url=args.rpc_url,
        static_dir=static,
    )
    print(f"GENESIS Security Lab on http://{args.host}:{args.port}" + ("" if static else "  (API only; frontend not built)"))
    uvicorn.run(create_app(config), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
