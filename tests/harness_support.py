"""Shared helpers for the scenario-harness tests."""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from genesis.harness.grading import TransferObservation
from genesis.harness.manifest import ScenarioManifest, load_manifest, parse_manifest

REPO = Path(__file__).resolve().parents[1]
SCENARIOS = REPO / "scenarios"
FIRST_TRANSFER = SCENARIOS / "first-local-transfer"

ETHER = 10**18
GWEI = 10**9

#: Normalized digest of a passing reference run of first-local-transfer v1.0.0. Observed
#: identically on Anvil 1.8.7 (gas price 2 gwei) and on the test double (1 gwei). Change it
#: only together with a deliberate change to the scenario or to the normalization rules.
REFERENCE_OUTCOME_DIGEST = "3be8fafd0bf120d17d18777e9ea98f66873dae9c9ffbf3a6e8f5fb42936fab59"
ALICE = "0x00000000000000000000000000000000000a11ce"
BOB = "0x0000000000000000000000000000000000000b0b"

_RAW = tomllib.loads((FIRST_TRANSFER / "scenario.toml").read_text(encoding="utf-8"))


def raw_manifest() -> dict[str, Any]:
    """A fresh, mutable copy of the bundled scenario as plain data."""
    return copy.deepcopy(_RAW)


def first_transfer() -> ScenarioManifest:
    return load_manifest(FIRST_TRANSFER)


def manifest_with(**changes: Any) -> ScenarioManifest:
    """The bundled scenario with top-level sections replaced or updated."""
    data = raw_manifest()
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key].update(value)
        else:
            data[key] = value
    return parse_manifest(data)


def observation(*, value: int = 3 * ETHER // 2, to: str = BOB, status: int = 1, gas_used: int = 21_000,
                gas_price: int = GWEI, tx_hash: str = "0x" + "aa" * 32, block_hash: str = "0x" + "bb" * 32,
                block_number: int = 1, sender_adjust: int = 0) -> TransferObservation:  # fmt: skip
    """A consistent observation of alice sending ``value`` to ``to`` (bob by default).

    ``sender_adjust`` shifts alice's final balance by a few wei to break the fee accounting.
    """
    fee = gas_used * gas_price
    moved = value if status == 1 else 0
    balances_after = {"alice": 10 * ETHER - moved - fee + sender_adjust, "bob": moved if to == BOB else 0}
    return TransferObservation(
        chain_id=31337,
        client_version="anvil/v0.0.0-test-double",
        tx_hash=tx_hash,
        tx_from=ALICE,
        tx_to=to,
        tx_value=value,
        tx_nonce=0,
        tx_gas_limit=21_000,
        tx_type=2,
        status=status,
        gas_used=gas_used,
        effective_gas_price=gas_price,
        block_number=block_number,
        block_hash=block_hash,
        balances_before={"alice": 10 * ETHER, "bob": 0},
        balances_after=balances_after,
        nonces_before={"alice": 0, "bob": 0},
        nonces_after={"alice": 1, "bob": 0},
    )
