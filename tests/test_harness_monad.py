"""Tests for the Monad Testnet adapter (``genesis.harness.monad``).

Everything here runs offline: the scenario runs against the in-repository
fake node (``tests/fake_anvil.py``) on a loopback port with chain id 10143,
and the signing tests use a dummy key derived from a public test string —
never a real or funded key — or mock ``cast`` out entirely. No test here
touches a live network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from genesis.harness.chain import JsonRpcClient
from genesis.harness.manifest import (
    ManifestError,
    load_manifest,
    parse_manifest,
)
from genesis.harness.monad import (
    MONAD_TESTNET_CHAIN_ID,
    CastNotFound,
    CastSigner,
    MonadChain,
    MonadEnvironment,
    MonadError,
    MonadRunner,
    PublicJsonRpcClient,
    cmd_anchor,
    explorer_tx_url,
    run_monad_scenario,
)
from genesis.harness.runner import run_scenario
from tests.fake_anvil import FakeAnvil, FakeAnvilServer
from tests.harness_support import first_transfer, raw_manifest

REPO = Path(__file__).resolve().parents[1]
FIRST_MONAD = REPO / "scenarios" / "first-monad-transfer"

#: A dummy key for tests, derived from a public string. It is not a secret,
#: it has never been funded, and it must never be used on a live network.
DUMMY_KEY = "0x" + hashlib.sha256(b"genesis monad test key - not a real key").hexdigest()


def monad_manifest():
    return load_manifest(FIRST_MONAD)


def test_monad_scenario_manifest_loads() -> None:
    manifest = monad_manifest()
    assert manifest.environment.kind == "monad"
    assert manifest.environment.chain_id == MONAD_TESTNET_CHAIN_ID == 10143
    assert manifest.scenario.id == "first-monad-transfer"
    assert manifest.grading.max_score == 13


def test_monad_environment_needs_chain_id_10143() -> None:
    data = raw_manifest()
    data["environment"] = {"kind": "monad", "chain_id": 31337}
    with pytest.raises(ManifestError, match="chain id 10143"):
        parse_manifest(data)


def test_monad_testnet_is_still_not_a_kind() -> None:
    data = raw_manifest()
    data["environment"] = {"kind": "monad-testnet", "chain_id": 10143}
    with pytest.raises(ManifestError, match="'monad-testnet' is not supported"):
        parse_manifest(data)


def test_anvil_scenario_is_unchanged() -> None:
    manifest = first_transfer()
    assert manifest.environment.kind == "anvil"
    assert manifest.environment.chain_id == 31337


def test_public_client_refuses_plain_http() -> None:
    with pytest.raises(MonadError, match="https://"):
        PublicJsonRpcClient("http://127.0.0.1:8545")


def test_explorer_url() -> None:
    assert explorer_tx_url("0x" + "ab" * 32) == "https://testnet.monadexplorer.com/tx/" + "0x" + "ab" * 32


def test_cast_signer_rejects_a_malformed_key() -> None:
    with pytest.raises(MonadError, match="64 hex digits"):
        CastSigner("not-a-key")


def test_cast_signer_rejects_a_missing_cast_binary() -> None:
    with pytest.raises(CastNotFound, match="cannot find"):
        CastSigner(DUMMY_KEY, cast_executable="definitely-not-cast")


def test_cast_signer_repr_never_contains_the_key() -> None:
    signer = CastSigner(DUMMY_KEY, cast_executable="cast")
    assert DUMMY_KEY not in repr(signer) and DUMMY_KEY[2:] not in repr(signer)


def test_cast_failure_redacts_the_key(monkeypatch) -> None:
    signer = CastSigner(DUMMY_KEY, cast_executable="cast")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr=f"boom {DUMMY_KEY} happened"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(MonadError) as caught:
        signer.send_transfer(rpc_url="https://example.invalid", to="0x" + "0b" * 20,
                             value_wei=1, gas_limit=21000)
    assert DUMMY_KEY not in str(caught.value) and DUMMY_KEY[2:] not in str(caught.value)
    assert "redacted" in str(caught.value)


def test_monad_chain_refuses_the_wrong_chain_id() -> None:
    with FakeAnvilServer(FakeAnvil(chain_id=31337)) as server:
        chain = MonadChain(JsonRpcClient(server.url))
        with pytest.raises(MonadError, match="chain id 31337"):
            chain.require_monad()


def test_monad_environment_has_no_reset() -> None:
    node = FakeAnvil(chain_id=10143)
    chain = MonadChain(node)
    environment = MonadEnvironment(chain, monad_manifest(), rpc_url="http://127.0.0.1:8545")
    assert environment.reset() is False
    assert "permanent" in environment.reset_note


def test_offline_monad_run_passes_without_a_key() -> None:
    node = FakeAnvil(chain_id=10143)
    with FakeAnvilServer(node) as server:
        report = run_monad_scenario(monad_manifest(), rpc_url=server.url)
    assert report["status"] == "passed" and report["error"] is None
    assert report["environment"]["kind"] == "monad"
    assert report["environment"]["chain_id"] == 10143
    assert report["summary"] == {
        "runs": 1, "passed_runs": 1, "score": 13, "max_score": 13, "pass_threshold": 13,
    }
    run = report["runs"][0]
    assert run["status"] == "passed"
    assert run["reset_verified"] is False
    assert run["normalized_digest"] is not None
    # No explorer link offline: the transaction never reached the public chain.
    assert "explorer_tx_url" not in report["environment"]
    assert node.sent == 1


def test_run_scenario_dispatches_monad_by_kind() -> None:
    node = FakeAnvil(chain_id=10143)
    with FakeAnvilServer(node) as server:
        report = run_scenario(monad_manifest(), rpc_url=server.url)
    assert report["status"] == "passed"
    assert report["scenario"]["id"] == "first-monad-transfer"


def test_monad_run_cannot_repeat() -> None:
    with pytest.raises(ValueError, match="cannot repeat"):
        run_monad_scenario(monad_manifest(), repeat=2, rpc_url="http://127.0.0.1:8545")


def test_public_run_without_a_key_is_an_error_not_a_send(monkeypatch) -> None:
    monkeypatch.delenv("GENESIS_MONAD_PRIVATE_KEY", raising=False)
    report = run_monad_scenario(monad_manifest(), rpc_url="https://testnet-rpc.monad.xyz")
    assert report["status"] == "error"
    assert "GENESIS_MONAD_PRIVATE_KEY" in (report["error"] or "")
    assert report["runs"] == []


def test_a_signer_for_the_wrong_address_is_rejected() -> None:
    class WrongSigner:
        def address(self) -> str:
            return "0x" + "0b" * 20  # bob's address, not alice's

        def send_transfer(self, **kwargs) -> str:
            raise AssertionError("must not send when the address does not match")

    node = FakeAnvil(chain_id=10143)
    runner = MonadRunner(monad_manifest(), MonadChain(node), "http://127.0.0.1:8545",
                         signer=WrongSigner())
    from genesis.harness.runner import ReferenceActor

    result = runner.run_once(ReferenceActor())
    assert result.status == "rejected"
    assert "does not match" in result.problems[0] or "set the manifest" in result.problems[0]
    assert result.reset_verified is False
    assert node.sent == 0


def _anchor_args(**overrides):
    base = {
        "digest": "0x" + "cd" * 32,
        "day": 100,
        "population": 20,
        "trades": 3867,
        "contract": "0x" + "11" * 20,
        "rpc_url": "https://testnet-rpc.monad.xyz",
        "private_key": None,
        "cast": "cast",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_anchor_rejects_a_bad_digest() -> None:
    assert cmd_anchor(_anchor_args(digest="not-a-digest")) == 1


def test_anchor_rejects_a_missing_contract() -> None:
    assert cmd_anchor(_anchor_args(contract=None)) == 1


def test_anchor_rejects_a_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("GENESIS_MONAD_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GENESIS_MONAD_LEDGER", raising=False)
    assert cmd_anchor(_anchor_args()) == 1


def test_anchor_never_prints_the_key(monkeypatch, capsys) -> None:
    """A failing cast call must not leak the key into stdout/stderr."""
    monkeypatch.setenv("GENESIS_MONAD_PRIVATE_KEY", DUMMY_KEY)
    monkeypatch.setattr(
        CastSigner, "send_contract_call",
        lambda self, **kwargs: (_ for _ in ()).throw(MonadError(f"boom {DUMMY_KEY}")),
    )
    assert cmd_anchor(_anchor_args()) == 1
    captured = capsys.readouterr()
    assert DUMMY_KEY not in captured.out and DUMMY_KEY not in captured.err
