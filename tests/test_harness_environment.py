"""Environment initialization, verification and reset (against the Anvil test double)."""

from __future__ import annotations

import pytest

from genesis.harness.chain import AnvilChain, ChainError, to_hex
from genesis.harness.environment import ScenarioEnvironment, ScenarioSetupError
from tests.fake_anvil import FakeAnvil
from tests.harness_support import ALICE, BOB, ETHER, first_transfer


def setup(node: FakeAnvil | None = None) -> tuple[FakeAnvil, AnvilChain, ScenarioEnvironment]:
    node = node if node is not None else FakeAnvil()
    chain = AnvilChain(node)
    return node, chain, ScenarioEnvironment(chain, first_transfer())


def transfer(chain: AnvilChain, wei: int) -> None:
    chain.send_transaction({"from": ALICE, "to": BOB, "value": to_hex(wei), "gas": to_hex(21_000)})


def test_initialize_applies_and_verifies_the_initial_state() -> None:
    node, _, environment = setup()
    state = environment.initialize()
    assert {label: (s.address, s.balance, s.nonce) for label, s in state.items()} == {
        "alice": (ALICE, 10 * ETHER, 0),
        "bob": (BOB, 0, 0),
    }
    assert node.impersonated == {ALICE, BOB}
    assert environment.initialized and environment.client_version == "anvil/v0.0.0-test-double"
    assert node.calls.count("anvil_setBalance") == 2 and node.calls.count("evm_snapshot") == 1
    assert environment.verify() == []


def test_initialize_refuses_a_chain_with_another_id() -> None:
    _, _, environment = setup(FakeAnvil(chain_id=1))
    with pytest.raises(
        ScenarioSetupError, match="the chain has id 1, but scenario 'first-local-transfer' expects 31337"
    ):
        environment.initialize()


def test_initialize_refuses_nodes_that_are_not_anvil() -> None:
    _, _, environment = setup(FakeAnvil(client_version="Geth/v1.14.0"))
    with pytest.raises(ChainError, match="only drives Anvil"):
        environment.initialize()


def test_initialize_detects_an_account_that_is_not_fresh() -> None:
    node = FakeAnvil()
    node.nonces[ALICE] = 3
    _, _, environment = setup(node)
    with pytest.raises(ScenarioSetupError, match="alice: nonce is 3, expected 0"):
        environment.initialize()


def test_reset_restores_the_initial_state_repeatedly() -> None:
    node, chain, environment = setup()
    initial = environment.initialize()
    for _ in range(3):
        transfer(chain, ETHER)
        assert environment.state() != initial
        environment.reset()
        assert environment.state() == initial
        assert chain.block_number() == 0
    assert node.sent == 3


def test_reset_requires_initialization() -> None:
    _, _, environment = setup()
    with pytest.raises(ScenarioSetupError, match="has not been initialized"):
        environment.reset()


def test_reset_fails_loudly_if_the_snapshot_is_gone() -> None:
    node, _, environment = setup()
    environment.initialize()
    node.snapshots.clear()
    with pytest.raises(ScenarioSetupError, match="no longer has snapshot"):
        environment.reset()


def test_verify_reports_drift() -> None:
    node, _, environment = setup()
    environment.initialize()
    node.balances[BOB] = 5
    assert environment.verify() == ["bob: balance is 5 wei, expected 0"]
