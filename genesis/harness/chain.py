"""Local chain access: a JSON-RPC client, an Anvil adapter and ``anvil`` process control.

Phase 1 is local only, and this module enforces it: the client accepts only
``http://`` URLs on a loopback address, never routes requests through a proxy,
and the adapter refuses nodes that do not identify themselves as Anvil. There
are no private keys anywhere: scenario accounts are impersonated by Anvil.

The RPC methods used here were checked against Anvil's source
(``crates/anvil/core/src/eth/mod.rs`` in foundry-rs/foundry): ``evm_snapshot``
and ``evm_revert`` are aliases of ``anvil_snapshot`` / ``anvil_revert``, and a
snapshot is discarded when it is reverted to.
"""

from __future__ import annotations

import ipaddress
import itertools
import json
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Protocol

from genesis.models import GenesisError


class ChainError(GenesisError):
    """The local chain is unreachable, misbehaving, or not an allowed endpoint."""


#: User-Agent sent on every JSON-RPC request the harness makes. Monad's RPC
#: front door rejects requests carrying Python's default ``urllib`` agent
#: (HTTP 403), while ``curl``/``cast`` work fine; identifying the client
#: fixes that, and it costs nothing on a local Anvil node.
HARNESS_USER_AGENT = "genesis-harness/1.0"


class RpcError(ChainError):
    """The node answered a JSON-RPC call with an error."""

    def __init__(self, method: str, code: object, message: object) -> None:
        self.method = method
        self.code = code
        self.message = str(message)
        super().__init__(f"{method} failed: {message} (code {code})")


class AnvilNotFound(ChainError):
    """The ``anvil`` executable is not installed or not on PATH."""


def require_loopback_url(url: str) -> str:
    """Return ``url`` if it is an ``http://`` URL on a loopback address, else raise."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if parts.scheme != "http" or not loopback:
        raise ChainError(
            f"refusing RPC endpoint {url!r}: Phase 1 only talks to a local chain at http://127.0.0.1"
        )
    return url


def to_hex(value: int) -> str:
    """Encode an integer as a JSON-RPC quantity, e.g. ``21000 -> '0x5208'``."""
    if value < 0:
        raise ValueError("quantities cannot be negative")
    return hex(value)


def from_hex(value: object) -> int:
    """Decode a JSON-RPC quantity such as ``'0x5208'``."""
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ChainError(f"expected a hex quantity, got {value!r}")
    return int(value, 16)


class RpcClient(Protocol):
    def call(self, method: str, *params: object) -> Any: ...


class JsonRpcClient:
    """Minimal JSON-RPC 2.0 over HTTP, standard library only."""

    def __init__(self, url: str, *, timeout: float = 10.0) -> None:
        self.url = require_loopback_url(url)
        self.timeout = timeout
        # A local endpoint must never go through HTTP(S)_PROXY settings.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._ids = itertools.count(1)

    def call(self, method: str, *params: object) -> Any:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": list(params)}
        )
        request = urllib.request.Request(
            self.url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": HARNESS_USER_AGENT},
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise ChainError(f"{method}: HTTP {error.code} from {self.url}") from error
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise ChainError(f"cannot reach the local chain at {self.url}: {reason}") from error
        except json.JSONDecodeError as error:
            raise ChainError(f"{method}: the node did not return JSON") from error
        if not isinstance(body, dict):
            raise ChainError(f"{method}: malformed JSON-RPC response")
        error_body = body.get("error")
        if error_body is not None:
            if isinstance(error_body, dict):
                raise RpcError(method, error_body.get("code"), error_body.get("message"))
            raise RpcError(method, None, error_body)
        return body.get("result")


class AnvilChain:
    """Typed access to the few RPC methods the harness needs. Nothing else is exposed."""

    def __init__(self, rpc: RpcClient) -> None:
        self.rpc = rpc

    def client_version(self) -> str:
        return str(self.rpc.call("web3_clientVersion"))

    def require_anvil(self) -> str:
        """Return the client version, refusing any node that is not Anvil."""
        version = self.client_version()
        if not version.lower().startswith("anvil"):
            raise ChainError(f"refusing node {version!r}: the harness only drives Anvil development chains")
        return version

    def chain_id(self) -> int:
        return from_hex(self.rpc.call("eth_chainId"))

    def block_number(self) -> int:
        return from_hex(self.rpc.call("eth_blockNumber"))

    def balance(self, address: str) -> int:
        return from_hex(self.rpc.call("eth_getBalance", address, "latest"))

    def nonce(self, address: str) -> int:
        return from_hex(self.rpc.call("eth_getTransactionCount", address, "latest"))

    def code(self, address: str) -> str:
        return str(self.rpc.call("eth_getCode", address, "latest"))

    def set_balance(self, address: str, wei: int) -> None:
        self.rpc.call("anvil_setBalance", address, to_hex(wei))

    def impersonate(self, address: str) -> None:
        self.rpc.call("anvil_impersonateAccount", address)

    def snapshot(self) -> str:
        return str(self.rpc.call("evm_snapshot"))

    def revert(self, snapshot_id: str) -> bool:
        return bool(self.rpc.call("evm_revert", snapshot_id))

    def send_transaction(self, transaction: Mapping[str, str]) -> str:
        return str(self.rpc.call("eth_sendTransaction", dict(transaction)))

    def transaction(self, tx_hash: str) -> dict[str, Any]:
        result = self.rpc.call("eth_getTransactionByHash", tx_hash)
        if not isinstance(result, dict):
            raise ChainError(f"transaction {tx_hash} not found")
        return result

    def receipt(self, tx_hash: str, *, timeout: float = 10.0, poll: float = 0.05) -> dict[str, Any]:
        """Wait for a transaction's receipt. Anvil mines on every transaction by default."""
        deadline = time.monotonic() + timeout
        while True:
            result = self.rpc.call("eth_getTransactionReceipt", tx_hash)
            if isinstance(result, dict):
                return result
            if time.monotonic() >= deadline:
                raise ChainError(f"no receipt for {tx_hash} after {timeout} s")
            time.sleep(poll)


def free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


class AnvilProcess:
    """Starts a private ``anvil`` node on a loopback port and stops it again.

    Only well-established flags are passed: ``--host``, ``--port`` and
    ``--chain-id``. Output goes to a temporary file that is shown if start-up
    fails.
    """

    def __init__(self, executable: str = "anvil", *, chain_id: int = 31337, port: int | None = None,
                 startup_timeout: float = 30.0) -> None:  # fmt: skip
        self.executable = executable
        self.chain_id = chain_id
        self.port = port
        self.startup_timeout = startup_timeout
        self.url: str | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None

    def resolve_executable(self) -> str:
        found = shutil.which(self.executable)
        if found is None and Path(self.executable).is_file():
            found = self.executable
        if found is None:
            raise AnvilNotFound(
                f"cannot find {self.executable!r}; install Foundry (https://getfoundry.sh) "
                "or point --anvil at anvil.exe"
            )
        return found

    def start(self) -> str:
        if self._process is not None:
            raise ChainError("anvil is already running")
        executable = self.resolve_executable()
        port = self.port or free_port()
        command = [executable, "--host", "127.0.0.1", "--port", str(port), "--chain-id", str(self.chain_id)]
        self._log = tempfile.TemporaryFile()  # outlives this method; closed in stop()  # noqa: SIM115
        self._process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=self._log, stderr=subprocess.STDOUT
        )
        self.url = f"http://127.0.0.1:{port}"
        chain = AnvilChain(JsonRpcClient(self.url, timeout=2.0))
        deadline = time.monotonic() + self.startup_timeout
        while True:
            if self._process.poll() is not None:
                output = self.output()
                self.stop()
                raise ChainError(f"anvil exited during start-up: {output[-500:]}")
            try:
                chain.client_version()
                break
            except RpcError:
                break  # it answers; require_anvil below decides whether it is usable
            except ChainError:
                if time.monotonic() >= deadline:
                    self.stop()
                    raise ChainError(
                        f"anvil did not answer on {self.url} within {self.startup_timeout} s"
                    ) from None
                time.sleep(0.1)
        try:
            chain.require_anvil()
        except ChainError:
            self.stop()
            raise
        return self.url

    def output(self) -> str:
        if self._log is None:
            return ""
        self._log.seek(0)
        return self._log.read().decode("utf-8", errors="replace")

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if self._log is not None:
            self._log.close()
            self._log = None

    def __enter__(self) -> AnvilProcess:
        self.start()
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None,
                 traceback: TracebackType | None) -> None:  # fmt: skip
        self.stop()
