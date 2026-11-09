"""A test double for the subset of Anvil's JSON-RPC API the harness uses.

It lets the harness logic be tested without Foundry installed. It mirrors
Anvil's semantics for these methods: ``eth_sendTransaction`` needs an
impersonated (or dev) account, ``anvil_setBalance`` sets a balance, and
``evm_revert`` restores a snapshot and discards it together with every later
one. It is not a chain: it only performs plain value transfers. Behaviour on
real Anvil is covered separately by ``test_harness_anvil.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any

from genesis.harness.chain import RpcError

PLAIN_TRANSFER_GAS = 21_000


class FakeAnvil:
    def __init__(self, *, chain_id: int = 31337, client_version: str = "anvil/v0.0.0-test-double",
                 gas_price: int = 1_000_000_000) -> None:  # fmt: skip
        self.chain_id = chain_id
        self.client_version = client_version
        self.gas_price = gas_price
        self.balances: dict[str, int] = {}
        self.nonces: dict[str, int] = {}
        self.impersonated: set[str] = set()
        self.block_number = 0
        self.transactions: dict[str, dict[str, Any]] = {}
        self.receipts: dict[str, dict[str, Any]] = {}
        #: Headers of the most recent HTTP request, lower-cased names.
        #: Tests use this to assert what the harness clients actually send.
        self.last_request_headers: dict[str, str] = {}
        self.snapshots: dict[int, Any] = {}
        self.next_snapshot = 1
        self.sent = 0
        self.calls: list[str] = []

    def call(self, method: str, *params: Any) -> Any:
        self.calls.append(method)
        handler = getattr(self, f"_{method}", None)
        if handler is None:
            raise RpcError(method, -32601, "Method not found")
        return handler(*params)

    # --- state the tests can poke at --------------------------------------------------

    def _state(self) -> tuple[Any, ...]:
        return (self.balances, self.nonces, self.block_number, self.transactions, self.receipts)

    # --- the RPC methods ----------------------------------------------------------------

    def _web3_clientVersion(self) -> str:
        return self.client_version

    def _eth_chainId(self) -> str:
        return hex(self.chain_id)

    def _eth_blockNumber(self) -> str:
        return hex(self.block_number)

    def _eth_getBalance(self, address: str, block: str) -> str:
        return hex(self.balances.get(address.lower(), 0))

    def _eth_getTransactionCount(self, address: str, block: str) -> str:
        return hex(self.nonces.get(address.lower(), 0))

    def _eth_getCode(self, address: str, block: str) -> str:
        return "0x"

    def _anvil_setBalance(self, address: str, wei: str) -> None:
        self.balances[address.lower()] = int(wei, 16)

    def _anvil_impersonateAccount(self, address: str) -> None:
        self.impersonated.add(address.lower())

    def _evm_snapshot(self) -> str:
        snapshot_id = self.next_snapshot
        self.next_snapshot += 1
        self.snapshots[snapshot_id] = copy.deepcopy(self._state())
        return hex(snapshot_id)

    def _evm_revert(self, snapshot_id: str) -> bool:
        wanted = int(snapshot_id, 16)
        if wanted not in self.snapshots:
            return False
        state = copy.deepcopy(self.snapshots[wanted])
        self.balances, self.nonces, self.block_number, self.transactions, self.receipts = state
        self.snapshots = {key: value for key, value in self.snapshots.items() if key < wanted}
        return True

    def _eth_sendTransaction(self, request: dict[str, str]) -> str:
        sender, recipient = request["from"].lower(), request["to"].lower()
        if sender not in self.impersonated:
            raise RpcError("eth_sendTransaction", -32000, "no signer available")
        value = int(request["value"], 16)
        gas_limit = int(request["gas"], 16)
        if self.balances.get(sender, 0) < value + gas_limit * self.gas_price:
            raise RpcError("eth_sendTransaction", -32003, "insufficient funds for gas * price + value")
        nonce = self.nonces.get(sender, 0)
        fee = PLAIN_TRANSFER_GAS * self.gas_price
        self.balances[sender] -= value + fee
        self.balances[recipient] = self.balances.get(recipient, 0) + value
        self.nonces[sender] = nonce + 1
        self.block_number += 1
        seed = f"{sender}:{recipient}:{value}:{nonce}:{self.gas_price}:{self.block_number}"
        tx_hash = "0x" + hashlib.sha256(seed.encode()).hexdigest()
        self.transactions[tx_hash] = {
            "hash": tx_hash,
            "from": sender,
            "to": recipient,
            "value": hex(value),
            "nonce": hex(nonce),
            "gas": hex(gas_limit),
            "type": "0x2",
        }
        self.receipts[tx_hash] = {
            "transactionHash": tx_hash,
            "status": "0x1",
            "gasUsed": hex(PLAIN_TRANSFER_GAS),
            "effectiveGasPrice": hex(self.gas_price),
            "blockNumber": hex(self.block_number),
            "blockHash": "0x" + hashlib.sha256(f"block:{seed}".encode()).hexdigest(),
        }
        self.sent += 1
        return tx_hash

    def _eth_getTransactionByHash(self, tx_hash: str) -> dict[str, Any] | None:
        return self.transactions.get(tx_hash)

    def _eth_getTransactionReceipt(self, tx_hash: str) -> dict[str, Any] | None:
        return self.receipts.get(tx_hash)


class FakeAnvilServer:
    """Serves a :class:`FakeAnvil` over real HTTP JSON-RPC on a loopback port."""

    def __init__(self, node: FakeAnvil | None = None) -> None:
        self.node = node if node is not None else FakeAnvil()
        node_ref = self.node

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # name required by http.server
                node_ref.last_request_headers = {
                    key.lower(): value for key, value in self.headers.items()
                }
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                try:
                    reply = {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": node_ref.call(body["method"], *body["params"]),
                    }
                except RpcError as error:
                    reply = {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "error": {"code": error.code, "message": error.message},
                    }
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:  # silence request logs
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self) -> FakeAnvilServer:
        self.thread.start()
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None,
                 traceback: TracebackType | None) -> None:  # fmt: skip
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
