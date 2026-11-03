"""The JSON-RPC client, the local-only policy and anvil process control."""

from __future__ import annotations

import pytest

from genesis.harness.chain import (
    AnvilChain,
    AnvilNotFound,
    AnvilProcess,
    ChainError,
    JsonRpcClient,
    RpcError,
    free_port,
    from_hex,
    require_loopback_url,
    to_hex,
)
from tests.fake_anvil import FakeAnvilServer


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8545", "http://localhost:8545", "http://[::1]:8545", "http://127.0.0.2:1"]
)
def test_loopback_urls_are_accepted(url: str) -> None:
    assert require_loopback_url(url) == url


@pytest.mark.parametrize(
    "url",
    ["https://127.0.0.1:8545", "ws://127.0.0.1:8545", "http://example.com:8545", "http://10.0.0.5:8545",
     "http://192.168.1.2:8545", "http://127.0.0.1.example.com:8545", "http://0.0.0.0:8545", "127.0.0.1:8545"],
)  # fmt: skip
def test_anything_but_a_local_http_endpoint_is_refused(url: str) -> None:
    with pytest.raises(ChainError, match="refusing RPC endpoint"):
        JsonRpcClient(url)


def test_hex_quantities() -> None:
    assert to_hex(0) == "0x0" and to_hex(21_000) == "0x5208"
    assert from_hex("0x5208") == 21_000
    with pytest.raises(ValueError):
        to_hex(-1)
    with pytest.raises(ChainError):
        from_hex(21_000)


def test_client_round_trip_over_http() -> None:
    with FakeAnvilServer() as server:
        client = JsonRpcClient(server.url)
        assert client.call("eth_chainId") == "0x7a69"
        chain = AnvilChain(client)
        assert chain.chain_id() == 31337 and chain.require_anvil().startswith("anvil")
        with pytest.raises(RpcError, match="Method not found"):
            client.call("eth_doesNotExist")


def test_client_never_uses_a_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # nothing listens there
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    with FakeAnvilServer() as server:
        assert JsonRpcClient(server.url).call("eth_chainId") == "0x7a69"


def test_unreachable_node_is_a_clear_error() -> None:
    client = JsonRpcClient(f"http://127.0.0.1:{free_port()}", timeout=2)
    with pytest.raises(ChainError, match="cannot reach the local chain"):
        client.call("eth_chainId")


def test_missing_anvil_executable_is_reported() -> None:
    with pytest.raises(AnvilNotFound, match="install Foundry"):
        AnvilProcess("genesis-no-such-anvil-binary").start()
